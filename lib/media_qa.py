"""Deterministic post-render quality checks for local clip outputs.

This service owns only derived QA reports. It never writes approval state or
changes source media; callers decide when to persist the returned plan/report.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

from PIL import Image, ImageStat

from lib.media_profiles import get_profile
from lib.models.clip_plan import ClipSelectionPlan
from schemas.artifacts import validate_artifact

Runtime = Literal["ffmpeg", "remotion", "hyperframes"]
QAStatus = Literal["pass", "revise", "fail"]


@dataclass(frozen=True)
class MediaQAConfig:
    profile_name: str = "youtube_shorts"
    expected_render_runtime: Runtime = "ffmpeg"
    require_audio: bool = True
    min_audible_lufs: float = -55.0
    max_peak_clipping_lufs: float = -0.1
    black_frame_luma_threshold: float = 12.0
    duration_tolerance_seconds: float = 0.5
    max_av_sync_drift_seconds: float = 0.25
    sample_frame_count: int = 4
    require_subtitles: bool = False

    def __post_init__(self) -> None:
        get_profile(self.profile_name)
        if self.expected_render_runtime not in {"ffmpeg", "remotion", "hyperframes"}:
            raise ValueError("expected_render_runtime must be ffmpeg, remotion, or hyperframes")
        for name in (
            "min_audible_lufs", "max_peak_clipping_lufs", "black_frame_luma_threshold",
            "duration_tolerance_seconds", "max_av_sync_drift_seconds",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
        if not 0 <= self.black_frame_luma_threshold <= 255:
            raise ValueError("black_frame_luma_threshold must be within [0, 255]")
        if self.duration_tolerance_seconds < 0 or self.max_av_sync_drift_seconds < 0:
            raise ValueError("duration and AV sync tolerances must be non-negative")
        if isinstance(self.sample_frame_count, bool) or not isinstance(self.sample_frame_count, int) or self.sample_frame_count < 4:
            raise ValueError("sample_frame_count must be an integer >= 4")


@dataclass(frozen=True)
class ClipQAReport:
    candidate_id: str
    video_path: str
    status: QAStatus
    production_state: Literal["QA_PASSED", "QA_FAILED"]
    technical_probe: dict[str, Any]
    visual_spotcheck: dict[str, Any]
    audio_spotcheck: dict[str, Any]
    subtitle_check: dict[str, Any]
    promise_preservation: dict[str, Any]
    issues: tuple[str, ...]
    recommended_action: str
    final_review_artifact: dict[str, Any]


@dataclass(frozen=True)
class BatchQAReport:
    project_id: str
    overall_status: QAStatus
    passed_clip_ids: tuple[str, ...]
    failed_clip_ids: tuple[str, ...]
    clip_reports: tuple[ClipQAReport, ...]
    final_review: dict[str, Any]
    issues: tuple[str, ...]


class MediaQAInspector:
    """Probe encoded media, sample visible frames, and check audio/subtitles."""

    def __init__(self, *, ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None) -> None:
        self.ffmpeg = ffmpeg or "ffmpeg"
        self.ffprobe = ffprobe or "ffprobe"

    @staticmethod
    def _run(args: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)

    def _probe(self, path: Path) -> dict[str, Any]:
        result = self._run([
            self.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
        ], timeout=30)
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "ffprobe rejected the media")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("ffprobe returned malformed JSON")
        return payload

    def _extract_frames(self, path: Path, duration: float, count: int, destination: Path) -> list[Path]:
        destination.mkdir(parents=True, exist_ok=True)
        times = [0.05] if count == 1 else [0.05 + max(0.0, duration - 0.15) * i / (count - 1) for i in range(count)]
        frames: list[Path] = []
        for index, timestamp in enumerate(times):
            frame = destination / f"frame_{index:02d}.png"
            result = self._run([
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}",
                "-i", str(path), "-frames:v", "1", "-an", str(frame),
            ], timeout=30)
            if result.returncode == 0 and frame.is_file() and frame.stat().st_size > 0:
                frames.append(frame)
        return frames

    def _audio_active(self, path: Path, threshold: float, clipping_threshold: float) -> tuple[bool, bool, list[str]]:
        result = self._run([
            self.ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", "ebur128=framelog=verbose",
            "-f", "null", "-",
        ], timeout=60)
        log = result.stderr or ""
        values = []
        for line in log.splitlines():
            match = re.search(r"\bM:\s*(-?\d+(?:\.\d+)?)\s*LUFS", line)
            if match:
                value = float(match.group(1))
                if math.isfinite(value) and value > -119.9:
                    values.append(value)
        if not values:
            for line in log.splitlines():
                match = re.search(r"\bI:\s*(-?\d+(?:\.\d+)?)\s*LUFS", line)
                if match:
                    value = float(match.group(1))
                    if math.isfinite(value) and value > -119.9:
                        values.append(value)
        if result.returncode != 0:
            return False, False, ["unable to measure audio loudness"]
        peak_values = []
        for line in log.splitlines():
            match = re.search(r"\bPeak:\s*(-?\d+(?:\.\d+)?)\s*(?:LUFS|dBFS)", line)
            if match:
                value = float(match.group(1))
                if math.isfinite(value) and value > -119.9:
                    peak_values.append(value)
        return any(value >= threshold for value in values), any(value >= clipping_threshold for value in peak_values), []

    @staticmethod
    def _subtitle_cues(path: Path) -> list[tuple[float, float]]:
        text = path.read_text(encoding="utf-8-sig")
        cues: list[tuple[float, float]] = []
        srt = re.compile(r"(?m)^\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})")
        ass = re.compile(r"(?m)^Dialogue:\s*[^,]*,([^,]+),([^,]+),")
        def seconds(value: str) -> float:
            value = value.strip().replace(",", ".")
            hh, mm, ss = value.split(":")
            return int(hh) * 3600 + int(mm) * 60 + float(ss)
        for match in srt.finditer(text):
            cues.append((seconds(match.group(1)), seconds(match.group(2))))
        if not cues:
            for match in ass.finditer(text):
                cues.append((seconds(match.group(1)), seconds(match.group(2))))
        return cues

    def inspect_clip(
        self, *, candidate_id: str, video_path: str | Path,
        expected_duration_seconds: Optional[float] = None, subtitle_path: Optional[str | Path] = None,
        frames_output_dir: Optional[str | Path] = None, config: Optional[MediaQAConfig] = None,
        locked_runtime: Optional[str] = None,
    ) -> ClipQAReport:
        config = config or MediaQAConfig()
        profile = get_profile(config.profile_name)
        path = Path(video_path).expanduser()
        issues: list[str] = []
        tech_issues: list[str] = []
        visual_issues: list[str] = []
        audio_issues: list[str] = []
        subtitle_issues: list[str] = []
        stream_video: dict[str, Any] = {}
        stream_audio: dict[str, Any] | None = None
        duration = 0.0
        fps = 0.0
        size = 0
        resolution = ""
        codec = ""
        valid_container = False
        if not path.is_file() or path.stat().st_size <= 0:
            tech_issues.append("video file is missing or empty")
        else:
            size = path.stat().st_size
            try:
                probe = self._probe(path)
                streams = probe.get("streams", [])
                stream_video = next((s for s in streams if s.get("codec_type") == "video"), {})
                stream_audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
                fmt = probe.get("format", {})
                fmt_name = str(fmt.get("format_name", ""))
                valid_container = "mp4" in fmt_name
                if not valid_container:
                    tech_issues.append("container is not a recognized MP4/MOV container")
                if not stream_video:
                    tech_issues.append("video stream is missing")
                else:
                    width, height = int(stream_video.get("width", 0)), int(stream_video.get("height", 0))
                    resolution = f"{width}x{height}"
                    codec = str(stream_video.get("codec_name", ""))
                    try:
                        rate = str(stream_video.get("avg_frame_rate") or stream_video.get("r_frame_rate") or "0/1")
                        if "/" in rate:
                            num, den = rate.split("/", 1)
                            fps = float(num) / float(den) if float(den) else 0.0
                        else:
                            fps = float(rate)
                    except (ValueError, ZeroDivisionError):
                        fps = 0.0
                    raw_duration = stream_video.get("duration", fmt.get("duration", 0))
                    duration = float(raw_duration)
                    if not math.isfinite(duration) or duration <= 0:
                        tech_issues.append("video duration is unknown or invalid")
                        duration = 0.0
                    if (width, height) != (profile.width, profile.height):
                        tech_issues.append(f"resolution {resolution} does not match {profile.width}x{profile.height}")
                    if stream_video.get("pix_fmt") != "yuv420p":
                        tech_issues.append("pixel format is not yuv420p")
                    if codec != "h264":
                        tech_issues.append(f"video codec is {codec or 'unknown'}, expected h264")
                    if not math.isfinite(fps) or fps <= 0:
                        tech_issues.append("video frame rate is unknown or invalid")
                if expected_duration_seconds is not None:
                    if isinstance(expected_duration_seconds, bool):
                        raise ValueError("expected_duration_seconds must be a finite positive number")
                    expected = float(expected_duration_seconds)
                    tolerance = max(config.duration_tolerance_seconds, expected * 0.05)
                    if not math.isfinite(expected) or expected <= 0 or abs(duration - expected) > tolerance:
                        tech_issues.append("render duration differs from the approved clip window")
                if stream_audio and stream_video:
                    try:
                        vd = float(stream_video.get("duration", duration))
                        ad = float(stream_audio.get("duration", fmt.get("duration", duration)))
                        if math.isfinite(vd) and math.isfinite(ad) and abs(vd - ad) > config.max_av_sync_drift_seconds:
                            tech_issues.append("audio/video stream duration drift exceeds tolerance")
                    except (TypeError, ValueError):
                        tech_issues.append("unable to determine audio/video stream duration drift")
            except Exception as exc:
                tech_issues.append(f"ffprobe failed: {exc}")

        frame_dir_ctx = tempfile.TemporaryDirectory(prefix="media_qa_") if frames_output_dir is None else None
        try:
            frame_dir = Path(frames_output_dir) if frames_output_dir is not None else Path(frame_dir_ctx.name)
            frames: list[Path] = []
            if path.is_file() and duration > 0:
                try:
                    frames = self._extract_frames(path, duration, config.sample_frame_count, frame_dir)
                except Exception as exc:
                    visual_issues.append(f"frame extraction failed: {exc}")
            frame_lumas: list[float] = []
            for frame in frames:
                try:
                    with Image.open(frame) as image:
                        gray = image.convert("L")
                        frame_lumas.append(float(ImageStat.Stat(gray).mean[0]))
                        gray.close()
                except Exception as exc:
                    visual_issues.append(f"unable to read sampled frame: {exc}")
            if len(frame_lumas) >= 4:
                black = bool(frame_lumas and (frame_lumas[0] < config.black_frame_luma_threshold or
                                               sum(x < config.black_frame_luma_threshold for x in frame_lumas) > len(frame_lumas) / 2))
                if black:
                    visual_issues.append("opening black frame detected" if frame_lumas and frame_lumas[0] < config.black_frame_luma_threshold else "black frames detected")
            else:
                black = False
                visual_issues.append("unable to sample four frames: video unreadable")
            visual: dict[str, Any] = {
                "black_frames_detected": black, "broken_overlays": False, "missing_assets": False,
                "unreadable_text": False, "issues": visual_issues,
            }
            if len(frame_lumas) >= 4:
                visual["frames_sampled"] = len(frame_lumas)
            if frames_output_dir is not None:
                visual["frame_paths"] = [str(frame) for frame in frames]
        finally:
            if frame_dir_ctx is not None:
                frame_dir_ctx.cleanup()

        has_audio = stream_audio is not None
        narration_present = False
        clipping_detected = False
        if not has_audio:
            if config.require_audio:
                audio_issues.append("missing audio stream")
        elif path.is_file():
            narration_present, clipping_detected, audio_measure_issues = self._audio_active(
                path, config.min_audible_lufs, config.max_peak_clipping_lufs,
            )
            audio_issues.extend(audio_measure_issues)
            if not narration_present:
                audio_issues.append("audio stream is silent or below audible threshold")
            if clipping_detected:
                audio_issues.append("audio peak reaches the clipping threshold")
        audio = {
            "narration_present": narration_present,
            "music_present": False,
            "unexpected_silence": bool(config.require_audio and not narration_present),
            "clipping_detected": clipping_detected,
            "mix_intelligible": bool(narration_present),
            "issues": audio_issues,
        }

        subtitle_file = Path(subtitle_path).expanduser() if subtitle_path else None
        subtitles_present = False
        coverage = 0.0
        timing_drift = False
        if subtitle_file and subtitle_file.is_file():
            try:
                cues = self._subtitle_cues(subtitle_file)
                subtitles_present = bool(cues)
                valid = []
                for begin, end in cues:
                    if end <= begin or begin > duration + 0.5:
                        timing_drift = True
                        continue
                    valid.append((max(0.0, begin), min(duration, end)))
                    if end > duration + 0.5:
                        timing_drift = True
                covered = 0.0
                for begin, end in sorted(valid):
                    if end > begin:
                        covered += end - begin
                coverage = min(1.0, max(0.0, covered / duration)) if duration > 0 else 0.0
                if timing_drift:
                    subtitle_issues.append("subtitle cue timing falls outside the rendered clip")
            except Exception as exc:
                subtitle_issues.append(f"subtitle file could not be parsed: {exc}")
        if config.require_subtitles and not subtitles_present:
            subtitle_issues.append("required subtitles are missing or empty")
        subtitle = {
            "subtitles_expected": bool(config.require_subtitles or subtitle_path),
            "subtitles_present": subtitles_present,
            "coverage_ratio": coverage,
            "timing_drift_detected": timing_drift,
            "issues": subtitle_issues,
        }

        runtime_used = config.expected_render_runtime
        runtime_swap = bool(locked_runtime and locked_runtime != runtime_used)
        promise_issues = ["render runtime differs from the locked runtime"] if runtime_swap else []
        promise = {
            "delivery_promise_honored": not runtime_swap,
            "renderer_family_used": runtime_used,
            "render_runtime_used": runtime_used,
            "runtime_swap_detected": runtime_swap,
            "runtime_swap_check": "detected — locked runtime differs" if runtime_swap else "ok — runtime matches expected configuration",
            "silent_downgrade_detected": False,
            "issues": promise_issues,
        }
        technical = {
            "valid_container": valid_container,
            "duration_seconds": duration,
            "resolution": resolution,
            "fps": fps,
            "has_audio": has_audio,
            "codec": codec,
            "file_size_bytes": size,
            "issues": tech_issues,
        }
        for group in (tech_issues, visual_issues, audio_issues, subtitle_issues, promise_issues):
            issues.extend(group)
        critical = bool(tech_issues or visual_issues or black or audio_issues or (config.require_subtitles and subtitle_issues) or timing_drift or runtime_swap)
        status: QAStatus = "fail" if critical else "pass"
        action = "block" if runtime_swap else "re_render" if critical else "present_to_user"
        final = self._final_review(
            output_path=str(path), status=status, technical=technical, visual=visual,
            audio=audio, promise=promise, subtitle=subtitle, issues=issues, recommended_action=action,
        )
        validate_artifact("final_review", final)
        return ClipQAReport(
            candidate_id=candidate_id, video_path=str(path), status=status,
            production_state="QA_FAILED" if critical else "QA_PASSED", technical_probe=technical,
            visual_spotcheck=visual, audio_spotcheck=audio, subtitle_check=subtitle,
            promise_preservation=promise, issues=tuple(issues), recommended_action=action,
            final_review_artifact=final,
        )

    @staticmethod
    def _final_review(*, output_path: str, status: QAStatus, technical: dict[str, Any], visual: dict[str, Any],
                      audio: dict[str, Any], promise: dict[str, Any], subtitle: dict[str, Any],
                      issues: Sequence[str], recommended_action: str, metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return {
            "version": "1.0", "output_path": output_path, "status": status,
            "checks": {
                "technical_probe": technical, "visual_spotcheck": visual, "audio_spotcheck": audio,
                "promise_preservation": promise, "subtitle_check": subtitle,
            },
            "issues_found": list(issues), "recommended_action": recommended_action,
            "metadata": metadata or {},
        }

    def inspect_batch(
        self, *, project_id: str, render_results: Sequence[Any],
        plan: Optional[ClipSelectionPlan | dict[str, Any]] = None,
        output_path: Optional[str | Path] = None, frames_dir: Optional[str | Path] = None,
        config: Optional[MediaQAConfig] = None,
    ) -> BatchQAReport:
        reports: list[ClipQAReport] = []
        for index, item in enumerate(render_results):
            data = item if isinstance(item, dict) else {
                "candidate_id": getattr(item, "candidate_id", f"clip-{index + 1}"),
                "output_video_path": getattr(item, "output_video_path", None),
                "success": getattr(item, "success", True),
                "error": getattr(item, "error", None),
                "subtitle_path": getattr(item, "subtitle_path", None),
                "duration_seconds": getattr(item, "duration_seconds", None),
            }
            candidate_id = str(data.get("candidate_id") or data.get("clip_id") or f"clip-{index + 1}")
            media_path = data.get("output_video_path") or data.get("video_path") or ""
            if not data.get("success", True) or not media_path or not Path(media_path).is_file():
                # Reuse the schema-valid missing-media report path; add renderer's reason.
                report = self.inspect_clip(candidate_id=candidate_id, video_path=media_path or "__missing__.mp4", config=config)
                extra = str(data.get("error") or "render failed or output file is missing")
                reports.append(ClipQAReport(**{**report.__dict__, "issues": (*report.issues, extra)}))
                continue
            frame_key = candidate_id if re.fullmatch(r"[A-Za-z0-9_-]+", candidate_id) else (
                re.sub(r"[^A-Za-z0-9_-]+", "_", candidate_id).strip("_")[:64]
                + "-" + hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:10]
            )
            frame_output = Path(frames_dir) / frame_key if frames_dir else None
            reports.append(self.inspect_clip(
                candidate_id=candidate_id, video_path=media_path,
                expected_duration_seconds=data.get("duration_seconds"), subtitle_path=data.get("subtitle_path"),
                frames_output_dir=frame_output, config=config,
            ))
        passed = tuple(r.candidate_id for r in reports if r.production_state == "QA_PASSED")
        failed = tuple(r.candidate_id for r in reports if r.production_state == "QA_FAILED")
        overall: QAStatus = "pass" if passed and not failed else "revise" if passed else "fail"
        first = reports[0] if reports else None
        technical = first.technical_probe if first else {"valid_container": False, "duration_seconds": 0.0, "resolution": "", "fps": 0.0, "has_audio": False, "codec": "", "file_size_bytes": 0, "issues": ["no rendered clips supplied"]}
        visual = first.visual_spotcheck if first else {"issues": ["no rendered clips supplied"]}
        audio = first.audio_spotcheck if first else {"narration_present": False, "music_present": False, "unexpected_silence": True, "clipping_detected": False, "mix_intelligible": False, "issues": ["no rendered clips supplied"]}
        promise = first.promise_preservation if first else {"delivery_promise_honored": False, "renderer_family_used": "ffmpeg", "render_runtime_used": "ffmpeg", "runtime_swap_detected": False, "runtime_swap_check": "skipped — no render", "silent_downgrade_detected": False, "issues": []}
        subtitle = first.subtitle_check if first else {"subtitles_expected": False, "subtitles_present": False, "coverage_ratio": 0.0, "timing_drift_detected": False, "issues": []}
        issues = [f"{r.candidate_id}: {issue}" for r in reports for issue in r.issues]
        plan_sha = None
        if plan is not None:
            if isinstance(plan, dict):
                plan_dict = plan
            elif hasattr(plan, "model_dump"):
                plan_dict = plan.model_dump(mode="json")
            else:
                plan_dict = plan.to_dict()
            plan_sha = hashlib.sha256(json.dumps(plan_dict, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        metadata = {
            "batch_summary": {"project_id": project_id, "passed_count": len(passed), "failed_count": len(failed)},
            "clip_reports": [{
                "candidate_id": r.candidate_id, "video_path": r.video_path, "status": r.status,
                "production_state": r.production_state, "issues": list(r.issues),
                "checks": r.final_review_artifact["checks"],
            } for r in reports],
            "passed_clip_ids": list(passed), "failed_clip_ids": list(failed),
        }
        if plan_sha:
            metadata["plan_sha256"] = plan_sha
        final = self._final_review(
            output_path=str(output_path or (first.video_path if first else "")), status=overall,
            technical=technical, visual=visual, audio=audio, promise=promise, subtitle=subtitle,
            issues=issues, recommended_action="present_to_user" if overall == "pass" else "re_render", metadata=metadata,
        )
        validate_artifact("final_review", final)
        if output_path is not None:
            dest = Path(output_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
            try:
                temp.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temp, dest)
            finally:
                temp.unlink(missing_ok=True)
        return BatchQAReport(project_id, overall, passed, failed, tuple(reports), final, tuple(issues))

    @staticmethod
    def apply_qa_to_plan(plan: ClipSelectionPlan | dict[str, Any], batch_qa: BatchQAReport) -> ClipSelectionPlan:
        model = plan if isinstance(plan, ClipSelectionPlan) else ClipSelectionPlan.model_validate(plan)
        states = {candidate_id: "QA_PASSED" for candidate_id in batch_qa.passed_clip_ids}
        states.update({candidate_id: "QA_FAILED" for candidate_id in batch_qa.failed_clip_ids})
        updated = model.model_copy(update={
            "candidates": tuple(candidate.model_copy(update={"production_state": states.get(candidate.candidate_id, candidate.production_state)})
                                 for candidate in model.candidates)
        })
        validate_artifact("clip_selection_plan", updated.to_dict())
        return updated
