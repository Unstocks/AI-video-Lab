"""Active speaker attribution via mouth-region motion + 8 kHz audio RMS gating.

Zero-OpenCV design: decodes grayscale 480px video and 8 kHz mono s16le PCM
directly from FFmpeg pipes, and runs all attribution/normalization/hysteresis
in pure NumPy.

Used by Smart Reframe v2 to:
1. Gate 2-speaker ``SPLIT`` scenes via ``is_conversation()`` so a silent
   listener never wastes half the 9:16 frame.
2. Drive ``ALTERNATE`` hard-cut speaker tracking via ``hold(min_windows=3)`` +
   ``speaker_xs()``.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Sequence

import numpy as np

WINDOW_SECONDS: float = 0.4
AUDIO_FLOOR: float = 0.18
MIN_MARGIN: float = 0.15
MIN_SHARE: float = float(os.environ.get("SPLIT_MIN_SHARE", "0.20"))
ANALYSIS_WIDTH: int = 480


def mouth_region(
    box: Sequence[float],
    frame_w: int,
    frame_h: int,
    scale: float = 1.0,
) -> tuple[int, int, int, int]:
    """Return ``(x0, y0, x1, y1)`` pixel rect around the mouth of ``box=[x,y,w,h]``."""
    x, y, w, h = [float(v) / float(scale) for v in box]
    cx = x + w / 2.0
    mouth_y = y + h * 0.72
    half_w = w * 0.36
    half_h = h * 0.22

    x0 = int(max(0, min(cx - half_w, frame_w - 1)))
    x1 = int(max(x0 + 1, min(cx + half_w, frame_w)))
    y0 = int(max(0, min(mouth_y - half_h, frame_h - 1)))
    y1 = int(max(y0 + 1, min(mouth_y + half_h, frame_h)))
    return x0, y0, x1, y1


def audio_envelope(
    video_path: str,
    start_s: float,
    duration_s: float,
    window_s: float = WINDOW_SECONDS,
) -> list[float]:
    """Return per-window RMS audio loudness normalized to peak (or ``[]`` if silent/no audio)."""
    if duration_s <= 0:
        return []
    try:
        raw = subprocess.run(
            [
                "ffmpeg", "-v", "error",
                "-ss", f"{max(0.0, start_s):.4f}",
                "-t", f"{duration_s:.4f}",
                "-i", str(video_path),
                "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=300,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    if not raw:
        return []

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    per_window = max(1, int(8000 * window_s))
    n = len(samples) // per_window
    if n < 1:
        return []

    windows = samples[: n * per_window].reshape(n, per_window)
    rms = np.sqrt(np.mean(windows ** 2, axis=1))
    peak = float(rms.max())
    return (rms / peak).tolist() if peak > 0 else [0.0] * n


def normalise_activity(activity: Sequence[Sequence[float]]) -> list[list[float]]:
    """Rescale each speaker's mouth motion onto their own 20th-80th percentile spread.

    Eliminates lighting/contrast/box-size bias between left and right speakers.
    """
    if not activity:
        return []
    columns = np.asarray(activity, dtype=float)
    if columns.ndim != 2 or columns.shape[1] < 2:
        return [list(row) for row in activity]

    low = np.percentile(columns, 20, axis=0)
    high = np.percentile(columns, 80, axis=0)
    spread = np.where(high - low > 1e-6, high - low, 1.0)
    return np.clip((columns - low) / spread, 0.0, None).tolist()


def attribute_windows(
    activity: Sequence[Sequence[float]],
    loudness: Sequence[float],
    min_margin: float = MIN_MARGIN,
    audio_floor: float = AUDIO_FLOOR,
) -> list[int | None]:
    """Return ``0``, ``1``, or ``None`` (unclear / silent) per decision window."""
    verdicts: list[int | None] = []
    for i, pair in enumerate(activity):
        if loudness and i < len(loudness) and loudness[i] < audio_floor:
            verdicts.append(None)
            continue
        a, b = float(pair[0]), float(pair[1])
        total = a + b
        if total <= 0:
            verdicts.append(None)
            continue
        margin = abs(a - b) / total
        verdicts.append(None if margin < min_margin else (0 if a > b else 1))
    return verdicts


def shares(verdicts: Sequence[int | None]) -> tuple[float, float]:
    """Return ``(share0, share1)`` of attributed windows, or ``(0.0, 0.0)``."""
    counted = [v for v in verdicts if v is not None]
    if not counted:
        return 0.0, 0.0
    n = float(len(counted))
    return counted.count(0) / n, counted.count(1) / n


def is_conversation(verdicts: Sequence[int | None], min_share: float | None = None) -> bool:
    """Return True only when both speakers hold at least ``min_share`` of speech."""
    threshold = MIN_SHARE if min_share is None else float(min_share)
    a, b = shares(verdicts)
    return min(a, b) >= threshold


def hold(verdicts: Sequence[int | None], min_windows: int = 3) -> list[int | None]:
    """Smooth per-window verdicts so a new speaker must hold ``min_windows`` consecutively."""
    out: list[int | None] = []
    current: int | None = None
    pending: int | None = None
    run = 0
    for v in verdicts:
        if v is None or v == current:
            if v == current:
                pending, run = None, 0
            out.append(current)
            continue
        if v == pending:
            run += 1
        else:
            pending, run = v, 1
        if current is None or run >= min_windows:
            current, pending, run = v, None, 0
        out.append(current)

    if all(v is None for v in out):
        return out

    first = next(v for v in out if v is not None)
    return [first if v is None else v for v in out]


def speaker_xs(
    held: Sequence[int | None],
    centres: Sequence[Sequence[float]],
    crop_w: int,
    orig_w: int,
    n_frames: int,
    fps: float,
    window_s: float = WINDOW_SECONDS,
) -> list[int]:
    """Convert held per-window speaker indices into per-frame hard-cut crop X offsets."""
    xs: list[int] = []
    max_x = max(0, orig_w - crop_w)
    for f in range(n_frames):
        idx = min(int((f / fps) / window_s), len(held) - 1) if held else 0
        who = held[idx] if held else 0
        cx = float(centres[who if who is not None else 0][0])
        x = int(round(cx - crop_w / 2.0))
        xs.append(max(0, min(x, max_x)))
    return xs


def _probe_dimensions(video_path: str) -> tuple[int, int]:
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "quiet", "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json", str(video_path),
            ],
            text=True,
            timeout=15,
        )
        streams = json.loads(out).get("streams") or []
        if streams:
            return int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)
    except Exception:
        pass
    return 0, 0


def decode_activity(
    video_path: str,
    start_s: float,
    duration_s: float,
    boxes: Sequence[Sequence[float]],
    fps: float,
    window_s: float = WINDOW_SECONDS,
    *,
    orig_w: int | None = None,
    orig_h: int | None = None,
) -> list[list[float]]:
    """Decode grayscale 480px video via FFmpeg and score mouth-region frame deltas."""
    if not orig_w or not orig_h:
        orig_w, orig_h = _probe_dimensions(video_path)
    if not orig_w or not orig_h or duration_s <= 0:
        return []

    small_w = min(ANALYSIS_WIDTH, orig_w)
    small_w -= small_w % 2
    small_h = max(2, int(orig_h * small_w / orig_w))
    small_h += small_h % 2
    scale = orig_w / float(small_w)

    regions = [mouth_region(b, small_w, small_h, scale) for b in boxes]
    frame_bytes = small_w * small_h

    proc = subprocess.Popen(
        [
            "ffmpeg", "-v", "error",
            "-ss", f"{max(0.0, start_s):.4f}",
            "-t", f"{duration_s:.4f}",
            "-i", str(video_path),
            "-vf", f"scale={small_w}:{small_h}",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=frame_bytes * 4,
    )

    per_window = max(1, int(round(fps * window_s)))
    activity: list[list[float]] = []
    bucket: list[list[float]] = []
    prev: np.ndarray | None = None
    try:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(small_h, small_w)
            if prev is not None:
                bucket.append([
                    float(
                        np.mean(
                            np.abs(
                                frame[y0:y1, x0:x1].astype(np.int16)
                                - prev[y0:y1, x0:x1].astype(np.int16)
                            )
                        )
                    )
                    for x0, y0, x1, y1 in regions
                ])
            prev = frame
            if len(bucket) >= per_window:
                activity.append(np.mean(bucket, axis=0).tolist())
                bucket = []
    finally:
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            proc.wait(timeout=10)
        except Exception:
            pass

    if bucket:
        activity.append(np.mean(bucket, axis=0).tolist())
    return activity


def verdicts_for_scene(
    video_path: str,
    start_f: int,
    end_f: int,
    fps: float,
    centres: Sequence[Sequence[float]],
    *,
    orig_w: int | None = None,
    orig_h: int | None = None,
) -> list[int | None]:
    """Compute per-window speaker verdicts for a scene from its two face centres."""
    from lib.split_layout import as_box

    start_s = start_f / float(fps)
    duration_s = (end_f - start_f) / float(fps)
    boxes = [as_box(c) for c in centres]
    activity = decode_activity(
        video_path, start_s, duration_s, boxes, fps, orig_w=orig_w, orig_h=orig_h
    )
    loudness = audio_envelope(video_path, start_s, duration_s)
    return attribute_windows(normalise_activity(activity), loudness)

