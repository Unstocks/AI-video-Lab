"""Smart Reframe v2 Engine: analyze in Python, render natively per-scene in FFmpeg.

Pipeline:
  1. Compute delivery size (1080px floor, even dimensions) & check vertical passthrough.
  2. Obtain scene boundaries (explicit ``shot_cuts`` or ``SceneDetect`` + 0.4s short-scene merge).
  3. Forward-pass face sampling (``read_frames_at`` + ``MultiFaceDetector``) to classify
     each scene as ``TRACK`` (single speaker) or ``GENERAL`` (wide / multi-face / no-face).
  4. Upgrade qualifying 2-speaker ``GENERAL`` scenes to ``SPLIT`` via ``lib.split_layout``.
  5. Optional ``lib.active_speaker`` mouth-motion + 8kHz audio RMS gating:
     - Gates ``SPLIT`` via ``is_conversation()`` so silent listeners never waste half the screen.
     - Optional ``speaker_cut_mode=True`` converts ``SPLIT`` into ``ALTERNATE`` hard cuts.
  6. Downscaled <=640px ``SmoothedCameraman`` + ``SpeakerTracker`` trajectory pass on ``TRACK``
     scenes (with ``begin_scene()`` + ``tracker.reset()`` at every shot cut).
  7. Apply manual ``crop_overrides`` LAST so explicit human framing always wins.
  8. Optional ``lib.punch_in`` smoothstep emphasis zoom (audio + editorial transcript beats).
  9. Render each scene natively in FFmpeg (deduped ``sendcmd`` on ``crop@c``, quarter-res
     ``blurred_backdrop`` + 42%-height ``GENERAL`` bed, or ``split_filtergraph``), concat via
     stream-copy, attach source audio (``-c:a copy`` when upstream already normalized), scrub
     metadata, write ``+faststart``, and emit ``<output>.layout.json``.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from lib import active_speaker, layout_ranges, punch_in, split_layout
from lib.camera_tracker import SmoothedCameraman, SpeakerTracker
from lib.face_detector import MultiFaceDetector, read_frames_at
from lib.ffmpeg_profiles import (
    METADATA_SCRUB,
    QUALITY_FAST,
    audio_encode_args,
    blurred_backdrop,
    escape_filter_value,
    resolve_video_codec,
    video_encode_args,
)
from tools.analysis.scene_detect import SceneDetect, _merge_short_scenes

logger = logging.getLogger(__name__)

ANALYSIS_MAX_WIDTH: int = 640
DELIVERY_MIN_WIDTH: int = 1080
GENERAL_CONTENT_HEIGHT_RATIO: float = float(
    os.environ.get("GENERAL_CONTENT_HEIGHT_RATIO", "0.42")
)
DETECT_STRIDE: int = max(1, int(os.environ.get("DETECT_STRIDE", "4")))
_STATIC_LAYOUTS = frozenset({"GENERAL", "SPLIT", "ALTERNATE"})


# --- Pure CI-testable helpers ----------------------------------------------

def delivery_size(orig_w: int, orig_h: int, aspect_ratio: float) -> tuple[int, int]:
    """Return even ``(out_w, out_h)`` respecting a 1080px vertical delivery floor."""
    out_h = int(orig_h)
    out_w = int(out_h * float(aspect_ratio))
    if out_w > orig_w:
        out_w = int(orig_w)
        out_h = int(out_w / float(aspect_ratio))

    if out_w < DELIVERY_MIN_WIDTH:
        out_w = DELIVERY_MIN_WIDTH
        out_h = int(round(out_w / float(aspect_ratio)))

    return out_w + (out_w % 2), out_h + (out_h % 2)


def source_already_fits(orig_w: int, orig_h: int, aspect_ratio: float, tol: float = 0.01) -> bool:
    """True when the source is already at (or narrower than) the target aspect ratio."""
    if orig_w <= 0 or orig_h <= 0:
        return False
    return (orig_w / float(orig_h)) <= float(aspect_ratio) * (1.0 + float(tol))


def dedupe_sendcmd_lines(xs: Sequence[int], fps: float, target: str = "crop@c") -> list[str]:
    """Emit change-point-deduped ``sendcmd`` lines for horizontal crop position ``x``."""
    lines: list[str] = []
    prev: int | None = None
    for i, x in enumerate(xs):
        ix = int(x)
        if ix != prev:
            lines.append(f"{i / float(fps):.4f} {target} x {ix};")
            prev = ix
    return lines


def scene_frame_ranges(
    scene_boundaries: Sequence[tuple[int, int]],
    strategies: Sequence[str],
    total_frames: int,
) -> list[tuple[int, int, str]]:
    """Clamp scene frame ranges to ``[0, total_frames]`` and drop empty ranges."""
    ranges: list[tuple[int, int, str]] = []
    for i, (start_f, end_f) in enumerate(scene_boundaries):
        strategy = strategies[i] if i < len(strategies) else "TRACK"
        s = max(0, min(int(start_f), int(total_frames)))
        e = max(s, min(int(end_f), int(total_frames)))
        if e > s:
            ranges.append((s, e, strategy))
    return ranges


def full_width_content_height(orig_w: int, orig_h: int, out_w: int) -> int:
    """Even foreground height when the source's full width fills ``out_w``."""
    fg_h = int(round(out_w * orig_h / float(orig_w)))
    return fg_h + (fg_h % 2)


def general_content_band(
    out_w: int,
    out_h: int,
    orig_w: int | None = None,
    orig_h: int | None = None,
    content_h: int | None = None,
) -> tuple[int, list[float]]:
    """Compute foreground height and normalized ``[top_frac, bottom_frac]`` band."""
    fg_h = int(content_h) if content_h else int(out_h * GENERAL_CONTENT_HEIGHT_RATIO)
    if orig_w and orig_h:
        fg_h = max(fg_h, full_width_content_height(orig_w, orig_h, out_w))
    fg_h = min(out_h, fg_h + (fg_h % 2))
    top = max(0.0, (out_h - fg_h) / (2.0 * float(out_h)))
    bot = min(1.0, top + fg_h / float(out_h))
    return fg_h, [round(top, 4), round(bot, 4)]


def general_filtergraph(
    out_w: int,
    out_h: int,
    *,
    content_h: int | None = None,
    orig_w: int | None = None,
    orig_h: int | None = None,
) -> str:
    """Blurred-background GENERAL filtergraph with quarter-res blur + 42%-height floor."""
    fg_h, _band = general_content_band(
        out_w, out_h, orig_w=orig_w, orig_h=orig_h, content_h=content_h
    )
    return (
        f"[0:v]split=2[bga][fga];"
        f"[bga]{blurred_backdrop(out_w, out_h, 12.0)}[bg];"
        f"[fga]scale=-2:{fg_h},crop=w=min(iw\\,{out_w}):h=ih[fg];"
        f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2,setsar=1[v]"
    )


def apply_crop_overrides(
    xs: list[int | None],
    strategies: list[str],
    scene_boundaries: Sequence[tuple[int, int]],
    overrides: dict[str | int, Any] | None,
    crop_w: int,
    orig_w: int,
    *,
    orig_h: int | None = None,
    splits: dict[int, tuple[tuple[float, float, float, float], tuple[float, float, float, float]]] | None = None,
) -> tuple[list[int | None], list[str]]:
    """Apply manual per-scene crop overrides (single-crop fraction or top/bottom split).

    Runs LAST after automatic classification and active-speaker passes so human
    framing decisions always win. Malformed or out-of-range overrides are skipped.
    """
    max_x = max(0, int(orig_w) - int(crop_w))

    def _to_x(fraction: Any) -> int:
        val = max(0.0, min(1.0, float(fraction)))
        return max(0, min(int(round(val * orig_w - crop_w / 2.0)), max_x))

    for raw_idx, value in (overrides or {}).items():
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            continue
        if not (0 <= idx < len(scene_boundaries)):
            continue
        start_f, end_f = scene_boundaries[idx]
        end_f = min(end_f, len(xs))
        if end_f <= start_f:
            continue

        if isinstance(value, dict):
            mode = str(value.get("layout", "")).strip().lower()
            if mode == "general":
                strategies[idx] = "GENERAL"
                if splits is not None:
                    splits.pop(start_f, None)
                continue
            if "top" in value and "bottom" in value:
                if splits is None or not orig_h:
                    continue

                def _point(half: Any) -> tuple[float, float, float, float]:
                    if isinstance(half, dict):
                        fx = max(0.0, min(1.0, float(half["x"])))
                        fy = max(0.0, min(1.0, float(half.get("y", 0.5))))
                    else:
                        fx, fy = max(0.0, min(1.0, float(half))), 0.5
                    return (fx * orig_w, fy * orig_h, orig_w * 0.12, orig_h * 0.20)

                try:
                    centres = (_point(value["top"]), _point(value["bottom"]))
                except (KeyError, TypeError, ValueError):
                    continue
                splits[start_f] = centres
                strategies[idx] = "SPLIT"
                continue
            if "x" in value:
                value = value["x"]
            else:
                continue

        try:
            x = _to_x(value)
        except (TypeError, ValueError):
            continue
        xs[start_f:end_f] = [x] * (end_f - start_f)
        strategies[idx] = "TRACK"
        if splits is not None:
            splits.pop(start_f, None)

    return xs, strategies


def build_layout_ranges(
    ranges: Sequence[tuple[int, int, str]],
    fps: float,
    *,
    orig_w: int,
    orig_h: int,
    out_w: int,
    out_h: int,
) -> list[dict[str, Any]]:
    """Build normalised layout ranges for ``<output>.layout.json``."""
    _fg_h, general_band = general_content_band(out_w, out_h, orig_w=orig_w, orig_h=orig_h)
    entries: list[dict[str, Any]] = []
    for start_f, end_f, strategy in ranges:
        layout = strategy.lower()
        entry: dict[str, Any] = {
            "start": round(start_f / float(fps), 3),
            "end": round(end_f / float(fps), 3),
            "layout": layout if layout in layout_ranges.VALID_LAYOUTS else "track",
        }
        if entry["layout"] == "general":
            entry["content"] = list(general_band)
        entries.append(entry)
    return layout_ranges.normalise(entries)


# --- Video probing & analysis ----------------------------------------------

def _probe_video(video_path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_format", "-show_streams",
        "-of", "json", str(video_path),
    ]
    out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace", timeout=30)
    data = json.loads(out)
    streams = data.get("streams") or []
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v_stream:
        raise RuntimeError(f"No video stream found in {video_path}")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    w = int(v_stream["width"])
    h = int(v_stream["height"])
    rot = 0.0
    for sd in v_stream.get("side_data_list", []):
        if "rotation" in sd:
            rot = float(sd["rotation"])
            break
    if not rot:
        try:
            rot = float((v_stream.get("tags") or {}).get("rotate", 0))
        except (TypeError, ValueError):
            rot = 0.0
    if int(abs(rot)) % 180 == 90:
        w, h = h, w

    def _parse_rate(raw: Any) -> float:
        text = str(raw or "").strip()
        if not text:
            return 0.0
        try:
            if "/" in text:
                num, den = text.split("/", 1)
                d_val = float(den)
                return float(num) / d_val if d_val > 0 else 0.0
            return float(text)
        except (ValueError, ZeroDivisionError):
            return 0.0

    # Prefer avg_frame_rate on VFR sources so r_frame_rate (e.g. 90000/1) cannot explode durations.
    avg_fps = _parse_rate(v_stream.get("avg_frame_rate"))
    raw_fps = _parse_rate(v_stream.get("r_frame_rate"))
    if 1.0 <= avg_fps <= 240.0:
        fps = avg_fps
    elif 1.0 <= raw_fps <= 240.0:
        fps = raw_fps
    else:
        fps = 30.0

    duration = float(
        (data.get("format") or {}).get("duration")
        or v_stream.get("duration")
        or 0.0
    )
    nb_frames_raw = v_stream.get("nb_frames")
    if nb_frames_raw and str(nb_frames_raw).isdigit() and int(nb_frames_raw) > 0:
        total_frames = int(nb_frames_raw)
    else:
        total_frames = max(1, int(round(duration * fps)))
    if duration <= 0:
        duration = total_frames / fps

    return {
        "width": w,
        "height": h,
        "fps": fps,
        "duration": duration,
        "total_frames": total_frames,
        "has_audio": has_audio,
    }


def _detect_scene_boundaries(
    video_path: Path,
    fps: float,
    total_frames: int,
    shot_cuts: Sequence[float] | None = None,
) -> list[tuple[int, int]]:
    """Return merged ``[(start_frame, end_frame), ...]`` covering ``[0, total_frames]``."""
    if shot_cuts:
        cut_frames = sorted(
            {
                max(0, min(int(round(float(t) * fps)), total_frames))
                for t in shot_cuts
                if float(t) > 0.0
            }
        )
        points = [0] + [c for c in cut_frames if 0 < c < total_frames] + [total_frames]
        bounds = [(points[i], points[i + 1]) for i in range(len(points) - 1) if points[i + 1] > points[i]]
        return _merge_short_scenes(bounds, fps, min_sec=0.4) or [(0, total_frames)]

    try:
        sd = SceneDetect()
        with tempfile.TemporaryDirectory(prefix="reframe_sd_") as tmp:
            res = sd.execute({
                "input_path": str(video_path),
                "min_scene_length_seconds": 0.4,
                "output_path": str(Path(tmp) / "scenes.json"),
            })
        if res.success and res.data.get("scenes"):
            raw_bounds: list[tuple[int, int]] = []
            for sc in res.data["scenes"]:
                s_f = max(0, min(int(round(float(sc["start_seconds"]) * fps)), total_frames))
                e_f = max(s_f, min(int(round(float(sc["end_seconds"]) * fps)), total_frames))
                if e_f > s_f:
                    raw_bounds.append((s_f, e_f))
            if raw_bounds:
                raw_bounds[0] = (0, raw_bounds[0][1])
                raw_bounds[-1] = (raw_bounds[-1][0], total_frames)
                return _merge_short_scenes(raw_bounds, fps, min_sec=0.4)
    except Exception as exc:
        logger.warning("SceneDetect failed during Reframe v2 (%s); treating clip as one scene", exc)

    return [(0, total_frames)]


def _classify_scenes(
    video_path: Path,
    scene_boundaries: Sequence[tuple[int, int]],
    orig_w: int,
    detector: MultiFaceDetector,
) -> list[str]:
    """Classify each scene as ``TRACK`` (single dominant face) or ``GENERAL`` (0 or 2+ spread faces)."""
    if not detector.is_available():
        return ["TRACK"] * len(scene_boundaries)

    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return ["TRACK"] * len(scene_boundaries)

    plan: list[tuple[int, list[int]]] = []
    for i, (s_f, e_f) in enumerate(scene_boundaries):
        n = min(8, max(3, (e_f - s_f) // 12))
        last_f = max(s_f, e_f - 1)
        idxs = [int(round(f)) for f in np.linspace(s_f, last_f, n)]
        plan.append((i, idxs))

    strategies = ["TRACK"] * len(scene_boundaries)
    try:
        flat = [f_idx for _i, idxs in plan for f_idx in idxs]
        frames_iter = read_frames_at(cap, flat)
        for i, idxs in plan:
            single_hits = 0
            multi_hits = 0
            zero_hits = 0
            for _f_idx in idxs:
                frame = next(frames_iter, None)
                if frame is None or float(frame.mean()) < 16.0:
                    continue
                faces = [
                    c
                    for c in split_layout.dedupe_faces(detector.detect(frame))
                    if c["box"][2] >= split_layout.MIN_FACE_WIDTH * orig_w
                ]
                if len(faces) == 0:
                    zero_hits += 1
                elif len(faces) == 1:
                    single_hits += 1
                else:
                    # Two+ substantial faces -> candidate for GENERAL (and then SPLIT)
                    multi_hits += 1
            total = single_hits + multi_hits + zero_hits
            if total == 0:
                strategies[i] = "TRACK"
            elif multi_hits >= max(2, total * 0.45):
                strategies[i] = "GENERAL"
            elif single_hits == 0 and zero_hits > 0:
                strategies[i] = "GENERAL"
            else:
                strategies[i] = "TRACK"
    finally:
        cap.release()

    return strategies


def _compute_track_trajectory(
    video_path: Path,
    scene_boundaries: Sequence[tuple[int, int]],
    strategies: Sequence[str],
    orig_w: int,
    orig_h: int,
    out_w: int,
    out_h: int,
    total_frames: int,
    aspect_ratio: float,
    detector: MultiFaceDetector,
) -> tuple[list[int | None], int, int]:
    """Run <=640px forward-pass face tracking + ``SmoothedCameraman`` / ``SpeakerTracker``."""
    cameraman = SmoothedCameraman(out_w, out_h, orig_w, orig_h, aspect_ratio=aspect_ratio)
    tracker = SpeakerTracker()
    crop_w, crop_h = cameraman.crop_width, cameraman.crop_height

    if not detector.is_available() or not any(s == "TRACK" for s in strategies):
        center_x = max(0, (orig_w - crop_w) // 2)
        xs_default: list[int | None] = [
            None if (strategies[si] in _STATIC_LAYOUTS) else center_x
            for si, (s_f, e_f) in enumerate(scene_boundaries)
            for _ in range(e_f - s_f)
        ]
        while len(xs_default) < total_frames:
            xs_default.append(center_x)
        return xs_default[:total_frames], crop_w, crop_h

    # Collect sparse frames needed for TRACK scenes (scene starts + every DETECT_STRIDE)
    detect_frames: list[int] = []
    for si, (s_f, e_f) in enumerate(scene_boundaries):
        if strategies[si] in _STATIC_LAYOUTS:
            continue
        for f in range(s_f, min(e_f, total_frames)):
            if f == s_f or (f % DETECT_STRIDE == 0):
                detect_frames.append(f)

    detections_by_frame: dict[int, list[dict[str, Any]]] = {}
    if detect_frames:
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        if cap.isOpened():
            try:
                for f_idx, frame in zip(detect_frames, read_frames_at(cap, detect_frames)):
                    if frame is not None:
                        detections_by_frame[f_idx] = detector.detect(frame)
            finally:
                cap.release()

    xs: list[int | None] = [None] * total_frames
    for si, (s_f, e_f) in enumerate(scene_boundaries):
        strat = strategies[si] if si < len(strategies) else "TRACK"
        if strat in _STATIC_LAYOUTS:
            cameraman.current_center_x = orig_w / 2.0
            cameraman.target_center_x = orig_w / 2.0
            continue
        tracker.reset()
        cameraman.begin_scene()
        for f in range(s_f, min(e_f, total_frames)):
            if f in detections_by_frame:
                target_box = tracker.get_target(detections_by_frame[f], f, orig_w)
                if target_box:
                    cameraman.update_target(target_box)
            x1, _y1, _x2, _y2 = cameraman.get_crop_box(force_snap=(f == s_f))
            xs[f] = x1

    return xs, crop_w, crop_h


# --- Segment & final rendering ---------------------------------------------

def _run_ffmpeg_with_fallback(
    build_cmd: Any,
    requested_codec: str,
    timeout: int = 300,
) -> tuple[str, list[str]]:
    """Run FFmpeg command with automatic ``h264_nvenc`` -> ``libx264`` retry on failure."""
    effective = resolve_video_codec(requested_codec)
    warnings: list[str] = []
    cmd = build_cmd(effective)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )
    if proc.returncode == 0:
        return effective, warnings

    if effective == "h264_nvenc":
        warnings.append(f"h264_nvenc failed during reframing; retried with libx264: {proc.stderr[:200]}")
        cmd_cpu = build_cmd("libx264")
        proc2 = subprocess.run(
            cmd_cpu, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
        if proc2.returncode == 0:
            return "libx264", warnings
        raise RuntimeError(f"FFmpeg error (libx264 fallback): {proc2.stderr[:400]}")

    raise RuntimeError(f"FFmpeg error ({effective}): {proc.stderr[:400]}")


def render_reframe_v2(
    input_path: str | Path,
    output_path: str | Path,
    *,
    aspect_ratio: float = 9.0 / 16.0,
    target_width: int | None = None,
    target_height: int | None = None,
    codec: str = "auto",
    crf: int | None = None,
    audio_copy: bool = False,
    scrub_metadata: bool = True,
    shot_cuts: Sequence[float] | None = None,
    forced_layout: str | None = None,
    enable_punch_in: bool = False,
    punch_in_zoom: float | None = None,
    emphasis_times: Sequence[float] | None = None,
    enable_active_speaker: bool = True,
    speaker_cut_mode: bool = False,
    crop_overrides: dict[str | int, Any] | None = None,
    write_sidecar: bool = True,
) -> dict[str, Any]:
    """Execute the full Smart Reframe v2 pipeline and write ``<output>.layout.json``."""
    src = Path(input_path)
    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    info = _probe_video(src)
    orig_w: int = info["width"]
    orig_h: int = info["height"]
    fps: float = info["fps"]
    duration: float = info["duration"]
    total_frames: int = info["total_frames"]
    has_audio: bool = info["has_audio"]

    if target_width and target_height:
        out_w = int(target_width) + (int(target_width) % 2)
        out_h = int(target_height) + (int(target_height) % 2)
    else:
        out_w, out_h = delivery_size(orig_w, orig_h, aspect_ratio)

    warnings: list[str] = []

    # Fast path: vertical source already fits target aspect ratio (no pillarbox downgrade!)
    if source_already_fits(orig_w, orig_h, aspect_ratio) and not crop_overrides and not enable_punch_in:
        vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        audio_args = (
            (["-map", "0:a:0?", "-c:a", "copy"] if audio_copy else ["-map", "0:a:0?", *audio_encode_args(normalize=False)])
            if has_audio
            else ["-an"]
        )
        scrub_args = list(METADATA_SCRUB) if scrub_metadata else []

        def _build_passthrough(c: str) -> list[str]:
            return [
                "ffmpeg", "-y", "-i", str(src),
                "-map", "0:v:0",
                "-vf", vf,
                "-r", f"{fps:.6f}",
                "-fps_mode", "cfr",
                *video_encode_args(QUALITY_FAST, codec=c, crf=crf),
                *audio_args,
                *scrub_args,
                "-movflags", "+faststart",
                str(dst),
            ]

        enc_used, w_enc = _run_ffmpeg_with_fallback(_build_passthrough, codec)
        warnings.extend(w_enc)
        ranges_out = layout_ranges.normalise([{"start": 0.0, "end": round(duration, 3), "layout": "track"}])
        sidecar = layout_ranges.write(dst, ranges_out, punch_ins=[]) if write_sidecar else None
        return {
            "output": str(dst),
            "source_resolution": f"{orig_w}x{orig_h}",
            "output_resolution": f"{out_w}x{out_h}",
            "method": "reframe_v2_passthrough",
            "encoder_used": enc_used,
            "scene_count": 1,
            "layout_ranges": ranges_out,
            "layout_sidecar": str(sidecar) if sidecar else None,
            "punch_ins": [],
            "layout_summary": {"track": 1},
            "warnings": warnings,
        }

    # 1. Scene detection + short-scene merge
    scene_boundaries = _detect_scene_boundaries(src, fps, total_frames, shot_cuts=shot_cuts)

    # 2. Face classification + 2-speaker SPLIT detection (respecting explicit forced_layout!)
    splits: dict[int, tuple[tuple[float, float, float, float], tuple[float, float, float, float]]] = {}
    with MultiFaceDetector() as detector:
        if forced_layout == "single_crop":
            strategies = ["TRACK"] * len(scene_boundaries)
        elif forced_layout == "blurred_pillarbox":
            strategies = ["GENERAL"] * len(scene_boundaries)
        elif forced_layout == "stacked_split":
            strategies = ["SPLIT"] * len(scene_boundaries)
            for s_f, _e_f in scene_boundaries:
                splits[s_f] = (
                    (orig_w * 0.25, orig_h * 0.45, orig_w * 0.14, orig_h * 0.24),
                    (orig_w * 0.75, orig_h * 0.45, orig_w * 0.14, orig_h * 0.24),
                )
        else:
            strategies = _classify_scenes(src, scene_boundaries, orig_w, detector)
            found_splits = split_layout.detect_split_scenes(
                str(src), scene_boundaries, strategies, fps=fps, detector=detector
            )
            for idx, centres in found_splits.items():
                s_f, _e_f = scene_boundaries[idx]
                splits[s_f] = centres
                strategies[idx] = "SPLIT"

        # 3. Active-speaker mouth-motion + audio RMS gating for SPLIT scenes
        alternate_tracks: dict[int, list[int]] = {}
        cameraman_probe = SmoothedCameraman(out_w, out_h, orig_w, orig_h, aspect_ratio=aspect_ratio)
        crop_w, crop_h = cameraman_probe.crop_width, cameraman_probe.crop_height

        if enable_active_speaker and splits and forced_layout != "stacked_split":
            for idx, (s_f, e_f) in enumerate(scene_boundaries):
                if strategies[idx] != "SPLIT" or s_f not in splits:
                    continue
                centres = splits[s_f]
                try:
                    verdicts = active_speaker.verdicts_for_scene(
                        str(src), s_f, e_f, fps, centres, orig_w=orig_w, orig_h=orig_h
                    )
                except Exception as exc:
                    logger.warning("active_speaker analysis failed on scene %d (%s)", idx, exc)
                    continue

                if speaker_cut_mode:
                    held = active_speaker.hold(verdicts, min_windows=3)
                    if any(v is not None for v in held):
                        alternate_tracks[idx] = active_speaker.speaker_xs(
                            held, centres, crop_w, orig_w, e_f - s_f, fps
                        )
                        strategies[idx] = "ALTERNATE"
                        splits.pop(s_f, None)
                else:
                    # Gate SPLIT: only keep stacked split if both speakers actually participate
                    has_evidence = any(v is not None for v in verdicts)
                    if has_evidence and not active_speaker.is_conversation(verdicts):
                        strategies[idx] = "TRACK"
                        splits.pop(s_f, None)

        # 4. Downscaled <=640px SmoothedCameraman + SpeakerTracker trajectory on TRACK scenes
        xs, crop_w, crop_h = _compute_track_trajectory(
            src, scene_boundaries, strategies, orig_w, orig_h, out_w, out_h,
            total_frames, aspect_ratio, detector
        )

    # Inject ALTERNATE hard-cut trajectories
    for idx, alt_xs in alternate_tracks.items():
        s_f, e_f = scene_boundaries[idx]
        n = min(len(alt_xs), max(0, min(e_f, total_frames) - s_f))
        xs[s_f : s_f + n] = alt_xs[:n]

    # 5. Manual crop_overrides ALWAYS win
    xs, strategies = apply_crop_overrides(
        xs, strategies, scene_boundaries, crop_overrides, crop_w, orig_w,
        orig_h=orig_h, splits=splits,
    )

    clamped_ranges = scene_frame_ranges(scene_boundaries, strategies, total_frames)
    if not clamped_ranges:
        clamped_ranges = [(0, total_frames, "TRACK")]

    # 6. Punch-in emphasis beats (audio + editorial transcript beats)
    final_beats: list[float] = []
    if enable_punch_in:
        audio_beats = punch_in.emphasis_times(str(src), duration) if has_audio else []
        final_beats = punch_in.merge_emphasis_times(audio_beats, emphasis_times)

    # 7. Per-scene native FFmpeg render in neutral ASCII workspace (TRAP-05 safe)
    encoder_used = resolve_video_codec(codec)
    segment_codecs: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="reframe_v2_") as tmp_str:
        tmp_dir = Path(tmp_str)
        segment_paths: list[Path] = []
        default_x = max(0, (orig_w - crop_w) // 2)

        for seg_idx, (s_f, e_f, strategy) in enumerate(clamped_ranges):
            seg_start = s_f / float(fps)
            seg_out = tmp_dir / f"seg_{seg_idx:03d}.mp4"
            seg_frames = max(1, e_f - s_f)

            if strategy == "SPLIT" and s_f in splits:
                left_c, right_c = splits[s_f]
                fc = split_layout.split_filtergraph(orig_w, orig_h, out_w, out_h, left_c, right_c)
                filter_args = ["-filter_complex", fc, "-map", "[v]"]
            elif strategy == "GENERAL":
                fc = general_filtergraph(out_w, out_h, orig_w=orig_w, orig_h=orig_h)
                filter_args = ["-filter_complex", fc, "-map", "[v]"]
            else:
                # TRACK or ALTERNATE: deduped sendcmd (with optional punch-in w/h/x/y)
                seg_xs = [
                    int(xs[f]) if (f < len(xs) and xs[f] is not None) else default_x
                    for f in range(s_f, e_f)
                ]
                if not seg_xs:
                    seg_xs = [default_x]

                zooms = (
                    punch_in.zoom_curve(
                        seg_frames, fps, final_beats, max_zoom=punch_in_zoom, start_offset=seg_start
                    )
                    if final_beats
                    else [1.0] * seg_frames
                )
                has_zoom = any(z > 1.001 for z in zooms)
                if has_zoom:
                    boxes = punch_in.crop_boxes(seg_xs, zooms, crop_w, crop_h, orig_w, orig_h)
                    cmd_lines = punch_in.sendcmd_lines(boxes, fps, target="crop@c")
                    init_w, init_h, init_x, init_y = boxes[0]
                else:
                    cmd_lines = dedupe_sendcmd_lines(seg_xs, fps, target="crop@c")
                    init_w, init_h, init_x, init_y = crop_w, crop_h, seg_xs[0], 0

                if len(cmd_lines) > 1:
                    cmd_file = tmp_dir / f"cmd_{seg_idx:03d}.txt"
                    cmd_file.write_text("\n".join(cmd_lines) + "\n", encoding="utf-8")
                    esc = escape_filter_value(cmd_file)
                    vf = (
                        f"setpts=PTS-STARTPTS,"
                        f"sendcmd=f='{esc}',"
                        f"crop@c=w={init_w}:h={init_h}:x={init_x}:y={init_y},"
                        f"scale={out_w}:{out_h},setsar=1"
                    )
                else:
                    vf = (
                        f"setpts=PTS-STARTPTS,"
                        f"crop=w={init_w}:h={init_h}:x={init_x}:y={init_y},"
                        f"scale={out_w}:{out_h},setsar=1"
                    )
                filter_args = ["-vf", vf]

            # Exact frame-count output (-frames:v seg_frames after -i) prevents cumulative
            # +1/+2 frame B-frame drift across multi-scene non-keyframe cuts!
            def _build_seg(c: str, _s=seg_start, _nf=seg_frames, _fa=filter_args, _out=seg_out) -> list[str]:
                return [
                    "ffmpeg", "-y",
                    "-ss", f"{_s:.6f}",
                    "-i", str(src),
                    *_fa,
                    "-an",
                    "-r", f"{fps:.6f}",
                    "-fps_mode", "cfr",
                    "-frames:v", str(_nf),
                    *video_encode_args(QUALITY_FAST, codec=c, crf=crf),
                    str(_out),
                ]

            encoder_used, seg_warn = _run_ffmpeg_with_fallback(_build_seg, encoder_used)
            segment_codecs.add(encoder_used)
            warnings.extend(seg_warn)
            segment_paths.append(seg_out)

        # 8. Concat + map audio + scrub metadata + faststart
        # If NVENC fell back to libx264 mid-loop, re-encode cleanly at concat to avoid mismatched SPS/PPS!
        mixed_codecs = len(segment_codecs) > 1
        concat_video_args = (
            video_encode_args(QUALITY_FAST, codec="libx264", crf=crf)
            if mixed_codecs
            else ["-c:v", "copy"]
        )
        audio_args = (
            (["-map", "1:a:0?", "-c:a", "copy"] if audio_copy else ["-map", "1:a:0?", *audio_encode_args(normalize=False)])
            if has_audio
            else ["-an"]
        )
        scrub_args = list(METADATA_SCRUB) if scrub_metadata else []

        if len(segment_paths) == 1:
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", str(segment_paths[0]),
                "-i", str(src),
                "-map", "0:v:0",
                *audio_args,
                "-c:v", "copy",
                *scrub_args,
                "-movflags", "+faststart",
                str(dst),
            ]
        else:
            concat_file = tmp_dir / "concat.txt"
            concat_file.write_text(
                "".join(
                    f"file '{p.as_posix().replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
                    for p in segment_paths
                ),
                encoding="utf-8",
            )
            mux_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-i", str(src),
                "-map", "0:v:0",
                *audio_args,
                *concat_video_args,
                *scrub_args,
                "-movflags", "+faststart",
                str(dst),
            ]
        proc = subprocess.run(
            mux_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300
        )
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg concat/mux error: {proc.stderr[:400]}")

    ranges_out = build_layout_ranges(
        clamped_ranges, fps, orig_w=orig_w, orig_h=orig_h, out_w=out_w, out_h=out_h
    )
    sidecar = layout_ranges.write(dst, ranges_out, punch_ins=final_beats) if write_sidecar else None

    summary: dict[str, int] = {}
    for r in ranges_out:
        summary[r["layout"]] = summary.get(r["layout"], 0) + 1

    return {
        "output": str(dst),
        "source_resolution": f"{orig_w}x{orig_h}",
        "output_resolution": f"{out_w}x{out_h}",
        "method": "reframe_v2",
        "encoder_used": encoder_used,
        "scene_count": len(clamped_ranges),
        "layout_ranges": ranges_out,
        "layout_sidecar": str(sidecar) if sidecar else None,
        "punch_ins": final_beats,
        "layout_summary": summary,
        "warnings": warnings,
    }

