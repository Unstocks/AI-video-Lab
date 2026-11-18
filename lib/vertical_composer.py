"""Layer 2 service for deterministic, approval-gated vertical clip rendering."""

from __future__ import annotations

import json
import hashlib
import math
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from lib.media_profiles import MediaProfile, get_profile
from lib.models.clip_plan import ClipSelectionPlan
from lib.subtitle_styles import get_subtitle_style
from lib.ffmpeg_utils import escape_ffmpeg_filter_path
from lib import layout_ranges as _layout_ranges
from lib.ffmpeg_profiles import (
    METADATA_SCRUB,
    QUALITY,
    resolve_video_codec,
    video_encode_args,
)


def _default_bundled_fonts_dir() -> Optional[Path]:
    candidate = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    return candidate if candidate.is_dir() else None


@dataclass(frozen=True)
class VerticalRenderConfig:
    profile_name: str = "youtube_shorts"
    layout_mode: Literal["auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut"] = "single_crop"
    burn_subtitles: bool = True
    subtitle_format: Literal["ass", "srt"] = "ass"
    highlight_style: Literal["none", "word_by_word", "karaoke"] = "karaoke"
    font_name: str = "Noto Sans Devanagari"
    font_size: int = 64
    margin_v: int = 320
    margin_l: int = 80
    margin_r: int = 120
    max_words_per_cue: int = 6
    max_chars_per_line: int = 32
    crf: int = 20
    codec: str = "libx264"
    style_preset: Optional[str] = None
    fonts_dir: Optional[str] = None
    normalize_audio: bool = True
    scrub_metadata: bool = True
    enable_punch_in: bool = False
    punch_in_zoom: float = 1.12
    emphasis_times: Optional[tuple[float, ...]] = None
    enable_active_speaker: bool = True
    speaker_cut_mode: bool = False
    crop_overrides: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        get_profile(self.profile_name)
        if self.layout_mode not in ("auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut"):
            raise ValueError("unsupported layout_mode")
        if self.subtitle_format not in ("ass", "srt"):
            raise ValueError("subtitle_format must be ass or srt")
        if self.highlight_style not in ("none", "word_by_word", "karaoke"):
            raise ValueError("unsupported highlight_style")
        for name in ("font_size", "max_words_per_cue", "max_chars_per_line"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("margin_v", "margin_l", "margin_r"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if isinstance(self.crf, bool) or not isinstance(self.crf, int) or not 0 <= self.crf <= 51:
            raise ValueError("crf must be an integer from 0 to 51")
        if not self.codec.strip() or not self.font_name.strip():
            raise ValueError("codec and font_name must be non-empty")
        if not isinstance(self.burn_subtitles, bool):
            raise ValueError("burn_subtitles must be a boolean")
        if self.style_preset is not None:
            get_subtitle_style(self.style_preset)
        if self.fonts_dir is not None and (not isinstance(self.fonts_dir, str) or not self.fonts_dir.strip()):
            raise ValueError("fonts_dir must be a non-empty path string when provided")


@dataclass(frozen=True)
class ClipRenderResult:
    candidate_id: str
    success: bool
    output_video_path: Optional[str]
    subtitle_path: Optional[str]
    source_video_used: str
    layout_mode: str
    duration_seconds: Optional[float]
    width: Optional[int]
    height: Optional[int]
    subtitle_cue_count: int = 0
    effective_highlight_style: str = "none"
    error: Optional[str] = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerticalBatchRenderResult:
    project_id: str
    plan_sha256: str
    profile_name: str
    clips: tuple[ClipRenderResult, ...]
    succeeded_count: int
    failed_count: int
    warnings: tuple[str, ...] = ()


class VerticalClipComposer:
    """Compose approved clips through existing trim, reframe, and subtitle tools."""

    def __init__(self, *, trimmer=None, reframer=None, subtitle_gen=None) -> None:
        self._trimmer = trimmer
        self._reframer = reframer
        self._subtitle_gen = subtitle_gen

    @staticmethod
    def select_editing_source(
        source_video_path: str | Path, *, source_manifest: Optional[dict[str, Any] | str | Path] = None,
    ) -> Path:
        if isinstance(source_manifest, (str, Path)):
            loaded = json.loads(Path(source_manifest).expanduser().read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("source_manifest JSON must contain an object")
            source_manifest = loaded
        if source_manifest:
            proxy = source_manifest.get("proxy_video_path")
            if isinstance(proxy, str) and proxy.strip() and Path(proxy).is_file():
                return Path(proxy)
        master = Path(source_video_path)
        if not master.is_file():
            raise FileNotFoundError(f"source video not found: {master}")
        return master

    @staticmethod
    def _finite_time(value: Any, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
        return float(value)

    @staticmethod
    def _output_stem(candidate_id: str) -> str:
        """Keep familiar IDs readable and safely encode unusual schema-valid IDs."""
        if re.fullmatch(r"[A-Za-z0-9_-]+", candidate_id):
            return candidate_id
        readable = re.sub(r"[^A-Za-z0-9_-]+", "_", candidate_id).strip("_")[:64] or "clip"
        digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:10]
        return f"{readable}-{digest}"

    @staticmethod
    def _rebase_shot_cuts(cuts: Optional[Sequence[float]], start: float, end: float) -> list[float]:
        result = []
        for cut in cuts or ():
            value = VerticalClipComposer._finite_time(cut, "shot cut")
            if start < value < end:
                result.append(value - start)
        return result

    @staticmethod
    def _rebase_speaker_tracks(
        tracks: Optional[Sequence[dict[str, Any]]], start: float, end: float,
    ) -> list[dict[str, Any]]:
        result = []
        for item in tracks or ():
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if "timestamp_seconds" in row:
                timestamp = VerticalClipComposer._finite_time(row["timestamp_seconds"], "speaker timestamp")
                if start <= timestamp <= end:
                    row["timestamp_seconds"] = timestamp - start
                    result.append(row)
            elif "start_seconds" in row and "end_seconds" in row:
                track_start = VerticalClipComposer._finite_time(row["start_seconds"], "speaker start")
                track_end = VerticalClipComposer._finite_time(row["end_seconds"], "speaker end")
                if track_end < track_start:
                    raise ValueError("speaker track end must be >= start")
                clipped_start, clipped_end = max(start, track_start), min(end, track_end)
                if clipped_end > clipped_start:
                    row["start_seconds"] = clipped_start - start
                    row["end_seconds"] = clipped_end - start
                    result.append(row)
        return result

    def _get_trimmer(self):
        if self._trimmer is None:
            from tools.video.video_trimmer import VideoTrimmer
            tool = VideoTrimmer()
            original_run_command = tool.run_command

            def timed_run_command(command, *, timeout=None, cwd=None):
                return original_run_command(command, timeout=timeout or 600, cwd=cwd)

            tool.run_command = timed_run_command
            self._trimmer = tool
        return self._trimmer

    def _get_reframer(self):
        if self._reframer is None:
            from tools.video.auto_reframe import AutoReframe
            self._reframer = AutoReframe()
        return self._reframer

    def _get_subtitle_gen(self):
        if self._subtitle_gen is None:
            from tools.subtitle.subtitle_gen import SubtitleGen
            self._subtitle_gen = SubtitleGen()
        return self._subtitle_gen

    def render_clip(
        self, *, candidate_id: str, source_video_path: str | Path,
        start_seconds: float, end_seconds: float, output_dir: str | Path,
        transcript_segments: Sequence[dict[str, Any]] = (),
        config: Optional[VerticalRenderConfig] = None,
        shot_cuts: Optional[Sequence[float]] = None,
        speaker_tracks: Optional[Sequence[dict[str, Any]]] = None,
        source_manifest: Optional[dict[str, Any] | str | Path] = None,
    ) -> ClipRenderResult:
        config = config or VerticalRenderConfig()
        source_used = str(source_video_path)
        output_path: Optional[Path] = None
        subtitle_path: Optional[Path] = None
        cue_count = 0
        effective_style = "none"
        warnings: list[str] = []
        profile: MediaProfile = get_profile(config.profile_name)
        try:
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ValueError("candidate_id must be a non-empty string")
            start = self._finite_time(start_seconds, "start_seconds")
            end = self._finite_time(end_seconds, "end_seconds")
            if end <= start:
                raise ValueError("end_seconds must be greater than start_seconds")
            fonts_directory: Optional[Path] = None
            if config.fonts_dir is not None:
                fonts_directory = Path(config.fonts_dir).expanduser()
                if not fonts_directory.is_dir():
                    raise ValueError(f"fonts_dir is not an existing directory: {fonts_directory}")
            else:
                fonts_directory = _default_bundled_fonts_dir()
            duration = end - start
            if profile.max_duration_seconds is not None and duration > profile.max_duration_seconds:
                warnings.append(
                    f"clip duration {duration:.3f}s exceeds {profile.name} maximum "
                    f"{profile.max_duration_seconds:.0f}s"
                )
            source = self.select_editing_source(source_video_path, source_manifest=source_manifest)
            source_used = str(source)
            destination = Path(output_dir)
            destination.mkdir(parents=True, exist_ok=True)
            output_stem = self._output_stem(candidate_id)
            output_path = destination / f"{output_stem}.mp4"
            subtitle_path = destination / f"{output_stem}.{config.subtitle_format}"
            protected_sources = [Path(source_video_path), source]
            if source_manifest:
                for key in ("master_video_path", "proxy_video_path"):
                    value = source_manifest.get(key)
                    if isinstance(value, str) and value:
                        protected_sources.append(Path(value))
            resolved_output = output_path.resolve()
            if any(path.resolve() == resolved_output for path in protected_sources):
                raise ValueError("output path would overwrite master or proxy source media")

            with tempfile.TemporaryDirectory(prefix=f".{output_stem}-", dir=destination) as workspace:
                work = Path(workspace)
                staged_subtitle = work / f"subtitles.{config.subtitle_format}"
                render_tmp = work / "final.mp4"
                trimmed = work / "trimmed.mp4"
                reframed = work / "reframed.mp4"
                effective_codec = (
                    resolve_video_codec("auto")
                    if config.codec.strip().lower() == "auto"
                    else config.codec
                )
                trim_codec = "libx264" if effective_codec not in ("h264_nvenc", "libx264") else effective_codec
                trim_result = self._get_trimmer().execute({
                    "operation": "cut", "input_path": str(source), "output_path": str(trimmed),
                    "start_seconds": start, "end_seconds": end, "codec": trim_codec,
                    "normalize_audio": config.normalize_audio,
                    "scrub_metadata": config.scrub_metadata,
                })
                if not trim_result.success and trim_codec == "h264_nvenc":
                    warnings.append("h264_nvenc failed during trimming; retried with libx264")
                    trim_result = self._get_trimmer().execute({
                        "operation": "cut", "input_path": str(source), "output_path": str(trimmed),
                        "start_seconds": start, "end_seconds": end, "codec": "libx264",
                        "normalize_audio": config.normalize_audio,
                        "scrub_metadata": config.scrub_metadata,
                    })
                if not trim_result.success or not trimmed.is_file() or trimmed.stat().st_size <= 0:
                    raise RuntimeError(trim_result.error or "VideoTrimmer did not produce a non-empty clip")

                reframe_inputs: dict[str, Any] = {
                    "input_path": str(trimmed), "output_path": str(reframed),
                    "target_width": profile.width, "target_height": profile.height,
                    "layout_mode": config.layout_mode,
                    "shot_cuts": self._rebase_shot_cuts(shot_cuts, start, end),
                    "speaker_tracks": self._rebase_speaker_tracks(speaker_tracks, start, end),
                    "codec": effective_codec, "crf": config.crf,
                    "audio_copy": True, "scrub_metadata": config.scrub_metadata,
                }
                if config.enable_punch_in:
                    reframe_inputs["enable_punch_in"] = True
                    reframe_inputs["punch_in_zoom"] = config.punch_in_zoom
                    if config.emphasis_times:
                        reframe_inputs["emphasis_times"] = list(config.emphasis_times)
                if config.layout_mode in ("auto", "speaker_cut") or config.crop_overrides:
                    reframe_inputs["enable_active_speaker"] = config.enable_active_speaker
                    reframe_inputs["speaker_cut_mode"] = (
                        config.speaker_cut_mode or config.layout_mode == "speaker_cut"
                    )
                if config.crop_overrides:
                    reframe_inputs["crop_overrides"] = dict(config.crop_overrides)

                reframed_result = self._get_reframer().execute(reframe_inputs)
                if not reframed_result.success:
                    if effective_codec != "h264_nvenc":
                        raise RuntimeError(reframed_result.error or "AutoReframe failed")
                    warnings.append("h264_nvenc failed during reframing; retried with libx264")
                    effective_codec = "libx264"
                    reframed_result = self._get_reframer().execute({
                        **reframe_inputs,
                        "codec": "libx264",
                    })
                    if not reframed_result.success:
                        raise RuntimeError(reframed_result.error or "AutoReframe libx264 fallback failed")
                warnings.extend(reframed_result.data.get("warnings", []))
                reframed_source = Path(reframed_result.data.get("output", reframed))
                if not reframed_source.is_file() or reframed_source.stat().st_size <= 0:
                    raise RuntimeError("AutoReframe did not produce a non-empty clip")

                reframed_sidecar = _layout_ranges.sidecar_path(reframed_source)
                active_layout_ranges = (
                    reframed_result.data.get("layout_ranges")
                    or _layout_ranges.read(reframed_source)
                )

                subtitle_result = None
                if transcript_segments:
                    subtitle_inputs: dict[str, Any] = {
                        "segments": list(transcript_segments), "format": config.subtitle_format,
                        "clip_start_seconds": start, "clip_end_seconds": end,
                        "output_path": str(staged_subtitle), "highlight_style": config.highlight_style,
                    }
                    if active_layout_ranges and config.subtitle_format == "ass":
                        subtitle_inputs["layout_ranges"] = active_layout_ranges
                    if config.style_preset is None:
                        subtitle_inputs.update({
                            "max_words_per_cue": config.max_words_per_cue,
                            "max_chars_per_line": config.max_chars_per_line,
                        })
                    else:
                        subtitle_inputs["style_preset"] = config.style_preset
                        # The config's historical values are its defaults; omit them so the preset
                        # supplies its designer values. Non-default caller choices remain explicit.
                        for key, current, default in (
                            ("max_words_per_cue", config.max_words_per_cue, 6),
                            ("max_chars_per_line", config.max_chars_per_line, 32),
                            ("font_name", config.font_name, "Noto Sans Devanagari"),
                            ("font_size", config.font_size, 64),
                            ("margin_v", config.margin_v, 320),
                            ("margin_l", config.margin_l, 80),
                            ("margin_r", config.margin_r, 120),
                        ):
                            if current != default:
                                subtitle_inputs[key] = current
                    if config.subtitle_format == "ass":
                        subtitle_inputs.update({
                            "play_res_x": profile.width, "play_res_y": profile.height,
                        })
                        if fonts_directory is not None:
                            subtitle_inputs["fonts_dir"] = str(fonts_directory)
                        if config.style_preset is None:
                            subtitle_inputs.update({
                                "font_name": config.font_name, "font_size": config.font_size,
                                "margin_v": config.margin_v, "margin_l": config.margin_l,
                                "margin_r": config.margin_r,
                            })
                    subtitle_result = self._get_subtitle_gen().execute(subtitle_inputs)
                    if not subtitle_result.success:
                        raise RuntimeError(subtitle_result.error or "SubtitleGen failed")
                    cue_count = int(subtitle_result.data.get("cue_count", 0))
                    effective_style = subtitle_result.data.get("effective_highlight_style", "none")
                    warnings.extend(subtitle_result.data.get("warnings", []))
                elif config.burn_subtitles:
                    warnings.append("no transcript segments supplied; subtitle burn skipped")

                if config.burn_subtitles and cue_count > 0 and staged_subtitle.is_file():
                    # Neutral ASCII staging path avoids Windows apostrophe/Unicode filter quoting traps
                    burn_sub = work / f"subs_burn.{config.subtitle_format}"
                    shutil.copy2(staged_subtitle, burn_sub)
                    escaped_subtitle = self._escape_filter_path(burn_sub)
                    filter_name = "ass" if config.subtitle_format == "ass" else "subtitles"
                    vf = f"{filter_name}='{escaped_subtitle}'"
                    if fonts_directory is not None and config.subtitle_format == "ass":
                        escaped_fonts = self._escape_filter_path(fonts_directory)
                        vf = f"ass='{escaped_subtitle}':fontsdir='{escaped_fonts}'"

                    def _build_burn_cmd(codec_choice: str) -> list[str]:
                        cmd = [
                            "ffmpeg", "-y", "-i", str(reframed_source),
                            "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
                            "-fps_mode", "cfr",
                            *video_encode_args(QUALITY, codec=codec_choice, crf=config.crf),
                            "-c:a", "copy",
                            *(METADATA_SCRUB if config.scrub_metadata else ()),
                            "-movflags", "+faststart", str(render_tmp),
                        ]
                        return cmd

                    try:
                        self._run_ffmpeg(_build_burn_cmd(effective_codec), timeout=600)
                    except Exception:
                        if effective_codec != "h264_nvenc":
                            raise
                        warnings.append("h264_nvenc failed during subtitle encoding; retried with libx264")
                        self._run_ffmpeg(_build_burn_cmd("libx264"), timeout=600)
                    if not render_tmp.is_file() or render_tmp.stat().st_size <= 0:
                        raise RuntimeError("subtitle burn produced no output file")
                else:
                    shutil.copy2(reframed_source, render_tmp)

                probe = self._probe_output(render_tmp)
                video = next((stream for stream in probe.get("streams", [])
                              if stream.get("codec_type") == "video"), None)
                if video is None:
                    raise RuntimeError("ffprobe found no video stream in rendered output")
                width, height = int(video["width"]), int(video["height"])
                if (width, height) != (profile.width, profile.height):
                    raise RuntimeError(f"unexpected output size {width}x{height}; expected {profile.width}x{profile.height}")
                if video.get("pix_fmt") != "yuv420p":
                    raise RuntimeError(f"unexpected pixel format {video.get('pix_fmt')!r}; expected 'yuv420p'")
                video_codec = video.get("codec_name")
                if video_codec != "h264":
                    raise RuntimeError(f"unexpected video codec {video_codec!r}; expected h264")
                media_duration = float(probe.get("format", {}).get("duration", 0))
                if not math.isfinite(media_duration) or media_duration <= 0:
                    raise RuntimeError("ffprobe returned an invalid output duration")
                if abs(media_duration - duration) > max(0.35, duration * 0.05):
                    warnings.append(
                        f"rendered duration {media_duration:.3f}s differs from requested {duration:.3f}s"
                    )
                audio_streams = [stream for stream in probe.get("streams", []) if stream.get("codec_type") == "audio"]
                if audio_streams and audio_streams[0].get("codec_name") != "aac":
                    warnings.append(f"audio codec is {audio_streams[0].get('codec_name')}, expected aac")
                if not audio_streams:
                    warnings.append("rendered clip contains no audio stream")
                promotions = [(render_tmp, output_path)]
                if staged_subtitle.is_file():
                    promotions.append((staged_subtitle, subtitle_path))
                if reframed_sidecar.is_file():
                    promotions.append((reframed_sidecar, _layout_ranges.sidecar_path(output_path)))
                backups: dict[Path, Path] = {}
                installed: list[Path] = []
                try:
                    for index, (_, final_path) in enumerate(promotions):
                        if final_path.exists():
                            backup = work / f"previous-{index}{final_path.suffix}"
                            os.replace(final_path, backup)
                            backups[final_path] = backup
                    for staged_path, final_path in promotions:
                        os.replace(staged_path, final_path)
                        installed.append(final_path)
                except Exception:
                    for final_path in reversed(installed):
                        final_path.unlink(missing_ok=True)
                    for final_path, backup in backups.items():
                        if backup.exists():
                            os.replace(backup, final_path)
                    raise
            try:
                from lib.events import emit_event, infer_project_dir

                proj_dir = infer_project_dir({"output_path": str(output_path), "output_dir": str(destination)})
                if proj_dir is not None:
                    layout_summary: dict[str, int] = {}
                    for r in active_layout_ranges or []:
                        lbl = str(r.get("layout", "track"))
                        layout_summary[lbl] = layout_summary.get(lbl, 0) + 1
                    emit_event(proj_dir, {
                        "type": "clip_rendered",
                        "candidate_id": candidate_id,
                        "encoder_used": effective_codec,
                        "layout_mode": config.layout_mode,
                        "layout_summary": layout_summary,
                        "punch_in_count": len(reframed_result.data.get("punch_ins") or []),
                        "output": str(output_path),
                    })
            except Exception:
                pass
            return ClipRenderResult(
                candidate_id, True, str(output_path), str(subtitle_path) if subtitle_result else None,
                source_used, config.layout_mode, media_duration, width, height,
                cue_count, effective_style, warnings=tuple(warnings),
            )
        except Exception as exc:
            return ClipRenderResult(
                candidate_id, False, None, None,
                source_used, config.layout_mode, None, None, None, cue_count, effective_style,
                error=str(exc), warnings=tuple(warnings),
            )

    def render_approved_batch(
        self, *, script: dict[str, Any], plan: ClipSelectionPlan | dict[str, Any],
        source_video_path: str | Path, output_dir: str | Path,
        transcript_segments: Sequence[dict[str, Any]] = (),
        config: Optional[VerticalRenderConfig] = None,
        shot_cuts: Optional[Sequence[float]] = None,
        speaker_tracks: Optional[Sequence[dict[str, Any]]] = None,
        source_manifest: Optional[dict[str, Any] | str | Path] = None,
    ) -> VerticalBatchRenderResult:
        from tools.analysis.clip_selector import verify_script_plan_sync

        # Governance check happens before source probing, directory creation, or FFmpeg.
        verify_script_plan_sync(script, plan, require_approved=True)
        normalized_plan = plan if isinstance(plan, ClipSelectionPlan) else ClipSelectionPlan.from_dict(plan)
        cfg = config or VerticalRenderConfig()
        candidate_map = {item.candidate_id: item for item in normalized_plan.candidates}
        clips: list[ClipRenderResult] = []
        for section in script["sections"]:
            candidate = candidate_map[section["id"]]
            clips.append(self.render_clip(
                candidate_id=candidate.candidate_id, source_video_path=source_video_path,
                start_seconds=section["start_seconds"], end_seconds=section["end_seconds"],
                output_dir=output_dir, transcript_segments=transcript_segments, config=cfg,
                shot_cuts=shot_cuts, speaker_tracks=speaker_tracks, source_manifest=source_manifest,
            ))
        succeeded = sum(clip.success for clip in clips)
        failed = len(clips) - succeeded
        batch_warnings = tuple(warning for clip in clips for warning in clip.warnings)
        return VerticalBatchRenderResult(
            normalized_plan.project_id, normalized_plan.compute_plan_sha256(), cfg.profile_name,
            tuple(clips), succeeded, failed, batch_warnings,
        )

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        return escape_ffmpeg_filter_path(path)

    @staticmethod
    def _run_ffmpeg(command: list[str], *, timeout: int) -> None:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "FFmpeg exited with a non-zero status").strip()
            raise RuntimeError(details[-4000:])

    @staticmethod
    def _probe_output(path: Path) -> dict[str, Any]:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "ffprobe failed").strip())
        return json.loads(result.stdout)
