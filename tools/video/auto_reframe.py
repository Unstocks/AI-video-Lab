"""Auto-reframe tool for aspect ratio conversion with face tracking.

Converts video between aspect ratios (e.g. 16:9 → 9:16 for Instagram Reels)
while keeping the speaker's face centered in frame. Uses face_tracker data
for smooth, content-aware cropping.

Primary use: converting talking-head footage shot in landscape to vertical
format for social media (TikTok, Reels, Shorts).

Approach: MediaPipe/OpenCV face detection → smoothed bounding box trajectory
→ FFmpeg crop filter. No GPU required.
"""

from __future__ import annotations

import json
import math
from fractions import Fraction
import tempfile
import time
from pathlib import Path
from typing import Any
from lib.ffmpeg_profiles import (
    METADATA_SCRUB,
    QUALITY_FAST,
    blurred_backdrop,
    video_encode_args,
)
from lib.ffmpeg_utils import escape_ffmpeg_filter_path

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolTier,
)


# Common target aspect ratios
ASPECT_PRESETS = {
    "portrait": (9, 16),       # Instagram Reels, TikTok, YouTube Shorts
    "square": (1, 1),          # Instagram Feed
    "landscape": (16, 9),      # YouTube, LinkedIn
    "cinematic": (21, 9),      # Ultra-wide
    "vertical_4_5": (4, 5),    # Instagram portrait post
}


class AutoReframe(BaseTool):
    name = "auto_reframe"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["cmd:ffmpeg"]
    install_instructions = (
        "FFmpeg is required. For face-tracked reframing, also install:\n"
        "pip install mediapipe opencv-python\n\n"
        "Without MediaPipe/OpenCV, falls back to center-crop."
    )
    agent_skills = ["ffmpeg"]

    capabilities = [
        "aspect_ratio_conversion",
        "face_tracked_crop",
        "smart_reframe",
        "center_crop",
        "shot_cut_reset",
        "speaker_track_crop",
        "blurred_pillarbox",
        "stacked_split",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {"type": "string"},
            "output_path": {"type": "string"},
            "target_aspect": {
                "type": "string",
                "enum": list(ASPECT_PRESETS.keys()),
                "default": "portrait",
                "description": "Target aspect ratio preset",
            },
            "target_width": {
                "type": "integer",
                "description": "Explicit target width (overrides preset)",
            },
            "target_height": {
                "type": "integer",
                "description": "Explicit target height (overrides preset)",
            },
            "face_tracking_json": {
                "type": "string",
                "description": "Path to pre-computed face_tracker JSON. If omitted, runs face detection internally.",
            },
            "smoothing_window": {
                "type": "integer",
                "default": 15,
                "minimum": 1,
                "description": "Number of frames for position smoothing (higher = smoother pan, lower = more responsive)",
            },
            "face_padding": {
                "type": "number",
                "default": 0.4,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Extra space around face as fraction of face size (0.4 = 40% padding)",
            },
            "sample_fps": {
                "type": "number",
                "default": 5,
                "description": "Face detection sample rate (only used if no face_tracking_json)",
            },
            "codec": {"type": "string", "default": "libx264"},
            "crf": {"type": "integer", "default": 18},
            "layout_mode": {
                "type": "string",
                "enum": ["auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut"],
                "default": "single_crop",
            },
            "enable_punch_in": {"type": "boolean", "default": False},
            "punch_in_zoom": {"type": "number", "minimum": 1.0, "maximum": 1.35, "default": 1.12},
            "emphasis_times": {"type": "array", "items": {"type": "number", "minimum": 0}},
            "enable_active_speaker": {"type": "boolean", "default": True},
            "speaker_cut_mode": {"type": "boolean", "default": False},
            "crop_overrides": {"type": "object"},
            "shot_cuts": {"type": "array", "items": {"type": "number", "minimum": 0}},
            "speaker_tracks": {
                "type": "array",
                "items": {
                    "oneOf": [
                        {"type": "object", "required": ["timestamp_seconds", "bbox"],
                         "properties": {"timestamp_seconds": {"type": "number", "minimum": 0},
                                        "bbox": {"$ref": "#/$defs/bbox"},
                                        "active": {"type": "boolean"},
                                        "speaker": {"type": ["string", "null"]}}},
                        {"type": "object", "required": ["start_seconds", "end_seconds", "bbox"],
                         "properties": {"start_seconds": {"type": "number", "minimum": 0},
                                        "end_seconds": {"type": "number", "minimum": 0},
                                        "bbox": {"$ref": "#/$defs/bbox"},
                                        "active": {"type": "boolean"},
                                        "speaker": {"type": ["string", "null"]}}},
                    ]
                },
            },
            "active_speaker_json": {"type": "string"},
            "split_left_center_x": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.25},
            "split_right_center_x": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.75},
            "audio_copy": {"type": "boolean", "default": False},
            "scrub_metadata": {"type": "boolean", "default": False},
        },
        "$defs": {"bbox": {"type": "object", "required": ["x", "y", "width", "height"],
                            "properties": {"x": {"type": "number"}, "y": {"type": "number"},
                                           "width": {"type": "number", "exclusiveMinimum": 0},
                                           "height": {"type": "number", "exclusiveMinimum": 0}}}},
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=0, disk_mb=4000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["FFmpeg error"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = [
        "input_path", "target_aspect", "target_width", "target_height",
        "smoothing_window", "face_padding", "face_tracking_json", "sample_fps",
        "codec", "crf", "layout_mode", "shot_cuts", "speaker_tracks",
        "active_speaker_json", "split_left_center_x", "split_right_center_x",
        "enable_punch_in", "punch_in_zoom", "emphasis_times",
        "enable_active_speaker", "speaker_cut_mode", "crop_overrides",
    ]
    side_effects = ["writes reframed video to output_path"]
    user_visible_verification = [
        "Play reframed output — verify face stays centered and framing is smooth",
        "Check that no important content is cropped out",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        start = time.time()
        layout_mode = inputs.get("layout_mode", "single_crop")
        if layout_mode not in {"auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut"}:
            return ToolResult(success=False, error=f"Unknown layout_mode: {layout_mode}")
        try:
            shot_cuts = self._validated_shot_cuts(inputs.get("shot_cuts", []))
            self._validate_split_centers(inputs)
            if "smoothing_window" in inputs:
                value = inputs["smoothing_window"]
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError("smoothing_window must be a positive integer")
            if "sample_fps" in inputs:
                self._finite_number(inputs["sample_fps"], "sample_fps", minimum=0.1)
            if "face_padding" in inputs:
                padding = self._finite_number(inputs["face_padding"], "face_padding", minimum=0)
                if padding > 1:
                    raise ValueError("face_padding must be between 0 and 1")
            if "punch_in_zoom" in inputs:
                pzoom = self._finite_number(inputs["punch_in_zoom"], "punch_in_zoom", minimum=1.0)
                if pzoom > 1.35:
                    raise ValueError("punch_in_zoom must be between 1.0 and 1.35")
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc))

        # Smart Reframe v2 route: auto, speaker_cut, punch-in, or manual crop_overrides
        use_v2 = (
            layout_mode in {"auto", "speaker_cut"}
            or bool(inputs.get("enable_punch_in", False))
            or bool(inputs.get("crop_overrides"))
        )
        if use_v2:
            aspect_name = inputs.get("target_aspect", "portrait")
            tw_a, th_a = ASPECT_PRESETS.get(aspect_name, (9, 16))
            explicit_w = inputs.get("target_width")
            explicit_h = inputs.get("target_height")
            aspect_ratio = (
                float(explicit_w) / float(explicit_h)
                if (explicit_w and explicit_h)
                else float(tw_a) / float(th_a)
            )
            output_path = Path(
                inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_{aspect_name}")))
            )
            try:
                from lib.reframe_v2 import render_reframe_v2

                v2_data = render_reframe_v2(
                    input_path,
                    output_path,
                    aspect_ratio=aspect_ratio,
                    target_width=explicit_w,
                    target_height=explicit_h,
                    codec=inputs.get("codec", "auto"),
                    crf=inputs.get("crf"),
                    audio_copy=bool(inputs.get("audio_copy", False)),
                    scrub_metadata=bool(inputs.get("scrub_metadata", True)),
                    shot_cuts=shot_cuts or None,
                    forced_layout=(
                        layout_mode
                        if layout_mode in {"single_crop", "blurred_pillarbox", "stacked_split"}
                        else None
                    ),
                    enable_punch_in=bool(inputs.get("enable_punch_in", False)),
                    punch_in_zoom=inputs.get("punch_in_zoom"),
                    emphasis_times=inputs.get("emphasis_times"),
                    enable_active_speaker=bool(inputs.get("enable_active_speaker", True)),
                    speaker_cut_mode=(
                        layout_mode == "speaker_cut"
                        or bool(inputs.get("speaker_cut_mode", False))
                    ),
                    crop_overrides=inputs.get("crop_overrides"),
                )
            except Exception as exc:
                return ToolResult(success=False, error=f"Reframe v2 error: {exc}")

            elapsed = time.time() - start
            artifacts = [str(output_path)]
            if v2_data.get("layout_sidecar"):
                artifacts.append(str(v2_data["layout_sidecar"]))
            return ToolResult(
                success=True,
                data={
                    "input": str(input_path),
                    **v2_data,
                    "target_aspect": aspect_name,
                },
                artifacts=artifacts,
                duration_seconds=round(elapsed, 2),
            )

        # Get source video dimensions
        src_w, src_h, src_fps, src_sar = self._get_video_info(input_path)
        if src_w == 0 or src_h == 0:
            return ToolResult(success=False, error="Could not read video dimensions")

        # Determine target crop dimensions (in source pixel space)
        target_w, target_h = self._compute_crop_size(inputs, src_w, src_h, src_sar)

        # Matching aspect can still require an explicitly requested resize.
        out_w, out_h = self._compute_output_resolution(inputs, target_w, target_h, src_w, src_h)
        needs_crop = target_w != src_w or target_h != src_h
        explicit_size = "target_width" in inputs and "target_height" in inputs
        if (
            layout_mode == "single_crop"
            and not shot_cuts
            and not inputs.get("speaker_tracks")
            and not inputs.get("active_speaker_json")
            and not inputs.get("face_tracking_json")
            and not needs_crop
            and src_sar == 1.0
            and (not explicit_size or (out_w, out_h) == (src_w, src_h))
        ):
            return ToolResult(
                success=True,
                data={"message": "Source already matches target aspect ratio", "output": str(input_path)},
                artifacts=[str(input_path)],
            )

        # Build output path
        aspect_name = inputs.get("target_aspect", "portrait")
        output_path = Path(
            inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_{aspect_name}")))
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Render via FFmpeg
        codec = inputs.get("codec", "libx264")
        crf = inputs.get("crf", 18)
        audio_copy = bool(inputs.get("audio_copy", False))
        scrub_metadata = bool(inputs.get("scrub_metadata", False))

        if layout_mode == "blurred_pillarbox":
            method = layout_mode
            result = self._render_blurred_pillarbox(
                input_path, output_path, src_w, src_h, out_w, out_h, codec, crf,
                audio_copy=audio_copy, scrub_metadata=scrub_metadata)
        elif layout_mode == "stacked_split":
            method = layout_mode
            result = self._render_stacked_split(
                input_path, output_path, src_w, src_h, src_sar, out_w, out_h,
                inputs.get("split_left_center_x", 0.25),
                inputs.get("split_right_center_x", 0.75), codec, crf,
                audio_copy=audio_copy, scrub_metadata=scrub_metadata)
        else:
            timestamps, crop_xs, crop_ys = self._get_tracking_samples(
                inputs, input_path, src_fps, src_w, src_h, target_w, target_h, shot_cuts)
            if len(crop_xs) >= 3:
                method = "face_tracked"
                crop_x, crop_y = crop_xs, crop_ys
                result = self._render_dynamic_crop(
                    input_path, output_path, crop_x, crop_y, timestamps,
                    target_w, target_h, out_w, out_h, src_fps, codec, crf,
                    audio_copy=audio_copy, scrub_metadata=scrub_metadata,
                )
            elif crop_xs:
                method = "face_tracked" if timestamps else "center_crop"
                crop_x = int(sum(crop_xs) / len(crop_xs))
                crop_y = int(sum(crop_ys) / len(crop_ys))
                result = self._render_static_crop(
                    input_path, output_path, crop_x, crop_y, target_w, target_h,
                    out_w, out_h, codec, crf,
                    audio_copy=audio_copy, scrub_metadata=scrub_metadata,
                )
            else:
                method = "center_crop"
                crop_x = (src_w - target_w) // 2
                crop_y = (src_h - target_h) // 2
                result = self._render_static_crop(
                    input_path, output_path, crop_x, crop_y, target_w, target_h,
                    out_w, out_h, codec, crf,
                    audio_copy=audio_copy, scrub_metadata=scrub_metadata,
                )

        if not result.success:
            return result

        elapsed = time.time() - start
        warnings = []
        if result.data and result.data.get("fallback"):
            warnings.append(result.data["fallback"])
        if method == "center_crop":
            warnings.append("face tracking/speaker tracks unavailable; used static center_crop")

        # Write layout sidecar for downstream seam subtitles and Studio UI timeline
        layout_label = {
            "stacked_split": "split",
            "blurred_pillarbox": "general",
        }.get(layout_mode, "track")
        out_ranges: list[dict[str, Any]] = []
        sidecar_str: str | None = None
        try:
            from lib import layout_ranges as _lr

            dur_s = self._probe_duration(output_path) or self._probe_duration(input_path)
            if dur_s > 0:
                entry: dict[str, Any] = {"start": 0.0, "end": round(dur_s, 3), "layout": layout_label}
                if layout_label == "general":
                    from lib.reframe_v2 import general_content_band
                    _fg_h, band = general_content_band(out_w, out_h, orig_w=src_w, orig_h=src_h)
                    entry["content"] = band
                out_ranges = _lr.normalise([entry])
                sidecar_str = str(_lr.write(output_path, out_ranges, punch_ins=[]))
        except Exception:
            pass

        legacy_artifacts = [str(output_path)]
        if sidecar_str:
            legacy_artifacts.append(sidecar_str)
        return ToolResult(
            success=True,
            data={
                "input": str(input_path),
                "output": str(output_path),
                "source_resolution": f"{src_w}x{src_h}",
                "crop_resolution": f"{target_w}x{target_h}",
                "output_resolution": f"{out_w}x{out_h}",
                "method": method,
                "target_aspect": inputs.get("target_aspect", "portrait"),
                "layout_ranges": out_ranges,
                "layout_sidecar": sidecar_str,
                "warnings": warnings,
            },
            artifacts=legacy_artifacts,
            duration_seconds=round(elapsed, 2),
        )

    def _probe_duration(self, path: Path) -> float:
        try:
            res = self.run_command(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "json", str(path)],
                timeout=15,
            )
            return float(json.loads(res.stdout).get("format", {}).get("duration") or 0.0)
        except Exception:
            return 0.0

    def _get_video_info(self, path: Path) -> tuple[int, int, float, float]:
        """Get encoded dimensions, FPS, and sample aspect ratio via ffprobe."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_streams",
            "-of", "json", str(path),
        ]
        try:
            result = self.run_command(cmd, timeout=30)
            data = json.loads(result.stdout)
            stream = data["streams"][0]
            w = int(stream["width"])
            h = int(stream["height"])
            rotation = 0.0
            for side_data in stream.get("side_data_list", []):
                if "rotation" in side_data:
                    rotation = float(side_data["rotation"])
                    break
            if not rotation:
                try:
                    rotation = float((stream.get("tags") or {}).get("rotate", 0))
                except (TypeError, ValueError):
                    rotation = 0.0
            if int(abs(rotation)) % 180 == 90:
                w, h = h, w
            # Parse r_frame_rate (e.g. "30000/1001")
            fps_parts = stream["r_frame_rate"].split("/")
            fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else float(fps_parts[0])
            # Unspecified sample aspect ratios are commonly reported as N/A
            # or 0:1; retain the existing square-pixel interpretation for them.
            try:
                sar = float(Fraction(stream.get("sample_aspect_ratio", "1:1").replace(":", "/")))
            except (ValueError, ZeroDivisionError):
                sar = 1.0
            if sar <= 0:
                sar = 1.0
            return w, h, fps, sar
        except Exception:
            return 0, 0, 30.0, 1.0

    def _compute_crop_size(
        self, inputs: dict[str, Any], src_w: int, src_h: int, src_sar: float = 1.0
    ) -> tuple[int, int]:
        """Compute crop dimensions in source pixel space that match the target aspect ratio."""
        if "target_width" in inputs and "target_height" in inputs:
            # Explicit dimensions — compute crop in source space matching this ratio
            tw, th = inputs["target_width"], inputs["target_height"]
        else:
            aspect_name = inputs.get("target_aspect", "portrait")
            tw, th = ASPECT_PRESETS.get(aspect_name, (9, 16))

        # Face positions and crop dimensions are encoded-pixel coordinates;
        # convert the requested display ratio into that coordinate space.
        target_ratio = (tw / th) / src_sar
        src_ratio = src_w / src_h

        if target_ratio > src_ratio:
            # Target is wider — crop height
            crop_w = src_w
            crop_h = int(src_w / target_ratio)
        else:
            # Target is taller/narrower — crop width
            crop_h = src_h
            crop_w = int(src_h * target_ratio)

        # Ensure even dimensions (required by most codecs)
        crop_w = crop_w - (crop_w % 2)
        crop_h = crop_h - (crop_h % 2)

        return crop_w, crop_h

    def _compute_output_resolution(
        self, inputs: dict[str, Any],
        crop_w: int, crop_h: int,
        src_w: int, src_h: int,
    ) -> tuple[int, int]:
        """Determine final output resolution. Scales to standard sizes."""
        if "target_width" in inputs and "target_height" in inputs:
            out_w = inputs["target_width"]
            out_h = inputs["target_height"]
        else:
            aspect_name = inputs.get("target_aspect", "portrait")
            if aspect_name == "portrait":
                out_w, out_h = 1080, 1920
            elif aspect_name == "square":
                out_w, out_h = 1080, 1080
            elif aspect_name == "landscape":
                out_w, out_h = 1920, 1080
            elif aspect_name == "cinematic":
                out_w, out_h = 2560, 1080
            elif aspect_name == "vertical_4_5":
                out_w, out_h = 1080, 1350
            else:
                out_w, out_h = crop_w, crop_h

        # Ensure even
        out_w = out_w - (out_w % 2)
        out_h = out_h - (out_h % 2)
        return out_w, out_h

    def _get_face_data(
        self, inputs: dict[str, Any], input_path: Path, src_fps: float
    ) -> list[dict]:
        """Resolve pluggable active-speaker/face tracks without ML dependencies."""
        sample_fps = inputs.get("sample_fps", 5)
        tracks = inputs.get("speaker_tracks")
        if tracks is not None:
            normalized = self._normalize_tracks(tracks, sample_fps)
            if normalized:
                return normalized

        active_path = inputs.get("active_speaker_json")
        if active_path and Path(active_path).is_file():
            try:
                payload = json.loads(Path(active_path).read_text(encoding="utf-8"))
                rows = payload.get("tracks", payload.get("faces", []))
                normalized = self._normalize_tracks(rows, sample_fps)
                if normalized:
                    return normalized
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        tracking_json = inputs.get("face_tracking_json")
        if tracking_json and Path(tracking_json).is_file():
            try:
                data = json.loads(Path(tracking_json).read_text(encoding="utf-8"))
                normalized = self._normalize_tracks(data.get("faces", []), sample_fps)
                if normalized:
                    return normalized
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        # Try to run face_tracker internally
        try:
            from tools.analysis.face_tracker import FaceTracker
            tracker = FaceTracker()
            if tracker.get_status().name == "UNAVAILABLE":
                return []
            result = tracker.execute({
                "input_path": str(input_path),
                "sample_fps": sample_fps,
            })
            if result.success and result.data:
                # Read the generated JSON
                output_file = result.data.get("output")
                if output_file:
                    data = json.loads(Path(output_file).read_text(encoding="utf-8"))
                    return self._normalize_tracks(data.get("faces", []), sample_fps)
        except Exception:
            pass

        return []

    @staticmethod
    def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if minimum is not None and value < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        return float(value)

    @classmethod
    def _validated_shot_cuts(cls, values: Any) -> list[float]:
        if not isinstance(values, (list, tuple)):
            raise TypeError("shot_cuts must be a list of timestamps")
        cuts = [cls._finite_number(value, "shot_cuts item", minimum=0) for value in values]
        if cuts != sorted(cuts) or len(set(cuts)) != len(cuts):
            raise ValueError("shot_cuts must be strictly increasing")
        return cuts

    @classmethod
    def _validate_split_centers(cls, inputs: dict[str, Any]) -> None:
        for name, default in (("split_left_center_x", 0.25), ("split_right_center_x", 0.75)):
            value = cls._finite_number(inputs.get(name, default), name, minimum=0)
            if value > 1:
                raise ValueError(f"{name} must be between 0 and 1")

    @classmethod
    def _normalize_tracks(cls, tracks: Any, sample_fps: float) -> list[dict]:
        if not isinstance(tracks, list):
            return []
        try:
            fps = cls._finite_number(sample_fps, "sample_fps", minimum=0.1)
        except ValueError:
            fps = 5.0
        active = [row for row in tracks if isinstance(row, dict) and row.get("active") is True]
        rows = active or [row for row in tracks if isinstance(row, dict)]
        result: list[dict] = []
        for row in rows:
            bbox = row.get("bbox")
            if not isinstance(bbox, dict):
                continue
            try:
                normalized_bbox = {key: cls._finite_number(bbox.get(key), f"bbox.{key}")
                                   for key in ("x", "y", "width", "height")}
                if normalized_bbox["width"] <= 0 or normalized_bbox["height"] <= 0:
                    continue
                if "timestamp_seconds" in row:
                    timestamp = cls._finite_number(row["timestamp_seconds"], "timestamp_seconds", minimum=0)
                    result.append({"timestamp_seconds": timestamp, "bbox": normalized_bbox})
                elif "start_seconds" in row and "end_seconds" in row:
                    start = cls._finite_number(row["start_seconds"], "start_seconds", minimum=0)
                    end = cls._finite_number(row["end_seconds"], "end_seconds", minimum=0)
                    if end < start:
                        continue
                    step = 1.0 / fps
                    count = max(1, int(math.floor((end - start) / step)) + 1)
                    result.extend({"timestamp_seconds": min(end, start + i * step), "bbox": normalized_bbox}
                                  for i in range(count))
                    if result and result[-1]["timestamp_seconds"] < end:
                        result.append({"timestamp_seconds": end, "bbox": normalized_bbox})
            except (TypeError, ValueError):
                continue
        result.sort(key=lambda item: item["timestamp_seconds"])
        return result

    def _get_tracking_samples(
        self, inputs: dict[str, Any], input_path: Path, src_fps: float,
        src_w: int, src_h: int, crop_w: int, crop_h: int,
        shot_cuts: list[float],
    ) -> tuple[list[float], list[int], list[int]]:
        faces = self._get_face_data(inputs, input_path, src_fps)
        if not faces:
            return [], [], []
        crop_x, crop_y = self._compute_face_tracked_crop(
            faces, src_w, src_h, crop_w, crop_h, src_fps,
            inputs.get("smoothing_window", 15), inputs.get("face_padding", 0.4), shot_cuts,
        )
        timestamps = [float(face["timestamp_seconds"]) for face in faces]
        if isinstance(crop_x, list):
            return timestamps, crop_x, crop_y
        return timestamps[:1], [crop_x], [crop_y]

    def _compute_face_tracked_crop(
        self,
        faces: list[dict],
        src_w: int, src_h: int,
        crop_w: int, crop_h: int,
        fps: float,
        smoothing_window: int,
        face_padding: float,
        shot_cuts: list[float] | None = None,
    ) -> tuple[list[int], list[int]]:
        """Compute smoothed crop positions from face tracking data.

        Returns a single (x, y) if face positions are stable enough,
        or lists of per-frame positions for dynamic cropping.
        """
        if not faces:
            cx = (src_w - crop_w) // 2
            cy = (src_h - crop_h) // 2
            return cx, cy

        # Convert relative bbox centers to pixel positions
        face_centers_x = []
        face_centers_y = []
        face_timestamps = []

        for f in faces:
            bbox = f["bbox"]
            # Center of face in pixel space
            center_x = (bbox["x"] + bbox["width"] / 2) * src_w
            center_y = (bbox["y"] + bbox["height"] / 2) * src_h
            face_centers_x.append(center_x)
            face_centers_y.append(center_y)
            face_timestamps.append(f["timestamp_seconds"])

        # Check if face position is stable (talking head usually is)
        x_range = max(face_centers_x) - min(face_centers_x)
        y_range = max(face_centers_y) - min(face_centers_y)

        # If face barely moves (<10% of frame), use a single static crop
        if x_range < src_w * 0.10 and y_range < src_h * 0.10:
            avg_x = sum(face_centers_x) / len(face_centers_x)
            avg_y = sum(face_centers_y) / len(face_centers_y)

            # Position crop window centered on face, with bias toward upper third
            crop_x = int(avg_x - crop_w / 2)
            crop_y = int(avg_y - crop_h * 0.35)  # Face in upper 35% of frame

            # Clamp to frame bounds
            crop_x = max(0, min(crop_x, src_w - crop_w))
            crop_y = max(0, min(crop_y, src_h - crop_h))

            return crop_x, crop_y

        # Dynamic crop: smooth the trajectory
        if shot_cuts:
            smoothed_x = self._smooth_positions_segmented(
                face_centers_x, face_timestamps, shot_cuts, smoothing_window)
            smoothed_y = self._smooth_positions_segmented(
                face_centers_y, face_timestamps, shot_cuts, smoothing_window)
        else:
            smoothed_x = self._smooth_positions(face_centers_x, smoothing_window)
            smoothed_y = self._smooth_positions(face_centers_y, smoothing_window)

        # Convert to crop positions (top-left corner), clamped
        crop_xs = []
        crop_ys = []
        for sx, sy in zip(smoothed_x, smoothed_y):
            cx = int(sx - crop_w / 2)
            cy = int(sy - crop_h * 0.35)
            cx = max(0, min(cx, src_w - crop_w))
            cy = max(0, min(cy, src_h - crop_h))
            crop_xs.append(cx)
            crop_ys.append(cy)

        return crop_xs, crop_ys

    def _smooth_positions(self, values: list[float], window: int) -> list[float]:
        """Simple moving average smoothing."""
        smoothed = []
        for i in range(len(values)):
            start = max(0, i - window // 2)
            end = min(len(values), i + window // 2 + 1)
            smoothed.append(sum(values[start:end]) / (end - start))
        return smoothed

    def _smooth_positions_segmented(
        self, values: list[float], timestamps: list[float], shot_cuts: list[float], window: int,
    ) -> list[float]:
        """Smooth independently inside each shot so a hard cut never bleeds."""
        if len(values) != len(timestamps):
            raise ValueError("timestamps and positions must have equal length")
        if not shot_cuts:
            return self._smooth_positions(values, window)
        groups: dict[int, list[int]] = {}
        for index, timestamp in enumerate(timestamps):
            shot_index = sum(timestamp >= cut for cut in shot_cuts)
            groups.setdefault(shot_index, []).append(index)
        result = list(values)
        for indexes in groups.values():
            smoothed = self._smooth_positions([values[i] for i in indexes], window)
            for index, value in zip(indexes, smoothed):
                result[index] = value
        return result

    @staticmethod
    def _audio_args(audio_copy: bool) -> list[str]:
        return ["-c:a", "copy"] if audio_copy else ["-c:a", "aac", "-b:a", "192k"]

    def _render_static_crop(
        self,
        input_path: Path, output_path: Path,
        crop_x: int, crop_y: int,
        crop_w: int, crop_h: int,
        out_w: int, out_h: int,
        codec: str, crf: int,
        *, audio_copy: bool = False, scrub_metadata: bool = False,
    ) -> ToolResult:
        """Render with a static crop position."""
        vf = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={out_w}:{out_h},setsar=1"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", vf,
            "-fps_mode", "cfr",
            *video_encode_args(QUALITY_FAST, codec=codec, crf=crf),
            *self._audio_args(audio_copy),
            *(METADATA_SCRUB if scrub_metadata else ()),
            "-movflags", "+faststart",
            str(output_path),
        ]

        try:
            self.run_command(cmd, timeout=600)
        except Exception as e:
            return ToolResult(success=False, error=f"FFmpeg render failed: {e}")

        return ToolResult(success=True)

    def _render_dynamic_crop(
        self,
        input_path: Path, output_path: Path,
        crop_xs: list[int], crop_ys: list[int],
        timestamps: list[float],
        crop_w: int, crop_h: int,
        out_w: int, out_h: int,
        fps: float,
        codec: str, crf: int,
        *, audio_copy: bool = False, scrub_metadata: bool = False,
    ) -> ToolResult:
        """Render with dynamic crop positions that follow the face."""
        if not crop_xs:
            return ToolResult(success=False, error="No crop positions computed")

        if len(crop_xs) < 3:
            avg_x = int(sum(crop_xs) / len(crop_xs))
            avg_y = int(sum(crop_ys) / len(crop_ys))
            return self._render_static_crop(
                input_path, output_path, avg_x, avg_y,
                crop_w, crop_h, out_w, out_h, codec, crf,
                audio_copy=audio_copy, scrub_metadata=scrub_metadata,
            )

        if len(timestamps) != len(crop_xs) or len(crop_xs) != len(crop_ys):
            return ToolResult(success=False, error="Tracking timestamps and crop positions must have equal length")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix=".reframe-", dir=output_path.parent) as workspace:
                sendcmd_path = Path(workspace) / "crop_commands.txt"
                lines = []
                prev_pair: tuple[int, int] | None = None
                for ts, cx, cy in zip(timestamps, crop_xs, crop_ys):
                    if prev_pair == (cx, cy):
                        continue
                    lines.append(f"{ts:.6f} [enter] crop x {cx};")
                    lines.append(f"{ts:.6f} [enter] crop y {cy};")
                    prev_pair = (cx, cy)
                sendcmd_path.write_text("\n".join(lines), encoding="utf-8")
                escaped = self._escape_ffmpeg_filter_path(sendcmd_path)
                vf = (
                    f"sendcmd=f='{escaped}':flags=enter,"
                    f"crop={crop_w}:{crop_h}:{crop_xs[0]}:{crop_ys[0]},"
                    f"scale={out_w}:{out_h},setsar=1"
                )
                cmd = [
                    "ffmpeg", "-y", "-i", str(input_path),
                    "-map", "0:v:0", "-map", "0:a?", "-vf", vf,
                    "-fps_mode", "cfr",
                    *video_encode_args(QUALITY_FAST, codec=codec, crf=crf),
                    *self._audio_args(audio_copy),
                    *(METADATA_SCRUB if scrub_metadata else ()),
                    "-movflags", "+faststart", str(output_path),
                ]
                self.run_command(cmd, timeout=600)
        except Exception:
            avg_x = int(sum(crop_xs) / len(crop_xs))
            avg_y = int(sum(crop_ys) / len(crop_ys))
            result = self._render_static_crop(
                input_path, output_path, avg_x, avg_y,
                crop_w, crop_h, out_w, out_h, codec, crf,
                audio_copy=audio_copy, scrub_metadata=scrub_metadata,
            )
            if result.success:
                result.data = result.data or {}
                result.data["fallback"] = "sendcmd failed, used static average crop"
            return result

        return ToolResult(success=True)

    @staticmethod
    def _escape_ffmpeg_filter_path(path: Path) -> str:
        return escape_ffmpeg_filter_path(path)

    def _render_blurred_pillarbox(
        self, input_path: Path, output_path: Path, src_w: int, src_h: int,
        out_w: int, out_h: int, codec: str, crf: int,
        *, audio_copy: bool = False, scrub_metadata: bool = False,
    ) -> ToolResult:
        # Quarter-res gblur (~45% less CPU) + 42%-height landscape foreground
        # floored at full-width height so portrait sources never shrink.
        full_w_h = int(round(out_w * src_h / float(src_w))) if src_w and src_h else 0
        full_w_h += full_w_h % 2
        fg_h = max(int(out_h * 0.42), full_w_h)
        fg_h += fg_h % 2
        fg_h = min(fg_h, out_h)
        vf = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]{blurred_backdrop(out_w, out_h, 12.0)}[bgb];"
            f"[fg]scale=-2:{fg_h},crop=w=min(iw\\,{out_w}):h=ih[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[vout]"
        )
        return self._render_filter_layout(
            input_path, output_path, vf, codec, crf,
            audio_copy=audio_copy, scrub_metadata=scrub_metadata,
        )

    def _render_stacked_split(
        self, input_path: Path, output_path: Path, src_w: int, src_h: int, src_sar: float,
        out_w: int, out_h: int, left_center: float, right_center: float,
        codec: str, crf: int,
        *, audio_copy: bool = False, scrub_metadata: bool = False,
    ) -> ToolResult:
        half_h = (out_h // 2) - ((out_h // 2) % 2)
        display_ratio = (out_w / half_h) / src_sar
        if src_w / src_h > display_ratio:
            crop_h = src_h - (src_h % 2)
            crop_w = int(crop_h * display_ratio)
        else:
            crop_w = src_w - (src_w % 2)
            crop_h = int(crop_w / display_ratio)
        crop_w -= crop_w % 2
        crop_h -= crop_h % 2
        if crop_w < 2 or crop_h < 2:
            return ToolResult(success=False, error="Source is too small for stacked_split crop")

        def x_for(center: float) -> int:
            x = int(center * src_w - crop_w / 2)
            x = max(0, min(x, src_w - crop_w))
            return x - (x % 2)

        y = max(0, (src_h - crop_h) // 2)
        y -= y % 2
        vf = (
            f"[0:v]split=2[left][right];"
            f"[left]crop={crop_w}:{crop_h}:{x_for(left_center)}:{y},scale={out_w}:{half_h}[top];"
            f"[right]crop={crop_w}:{crop_h}:{x_for(right_center)}:{y},scale={out_w}:{half_h}[bot];"
            f"[top][bot]vstack=inputs=2,pad={out_w}:{out_h}:0:0,setsar=1[vout]"
        )
        return self._render_filter_layout(
            input_path, output_path, vf, codec, crf,
            audio_copy=audio_copy, scrub_metadata=scrub_metadata,
        )

    def _render_filter_layout(
        self, input_path: Path, output_path: Path, vf: str, codec: str, crf: int,
        *, audio_copy: bool = False, scrub_metadata: bool = False,
    ) -> ToolResult:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_path), "-filter_complex", vf,
            "-map", "[vout]", "-map", "0:a?", "-fps_mode", "cfr",
            *video_encode_args(QUALITY_FAST, codec=codec, crf=crf),
            *self._audio_args(audio_copy),
            *(METADATA_SCRUB if scrub_metadata else ()),
            "-movflags", "+faststart",
            str(output_path),
        ]
        try:
            self.run_command(cmd, timeout=600)
        except Exception as exc:
            return ToolResult(success=False, error=f"FFmpeg render failed: {exc}")
        return ToolResult(success=True)

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        """Estimate runtime in seconds. Roughly 1x realtime for face tracking + render."""
        return 60.0  # Conservative default

    @staticmethod
    def list_presets() -> dict[str, str]:
        """Return available aspect ratio presets."""
        return {
            name: f"{w}:{h}"
            for name, (w, h) in ASPECT_PRESETS.items()
        }
