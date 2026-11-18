"""Smoothstep emphasis punch-in zoom for Smart Reframe v2.

Composes cleanly with the tracked crop trajectory by widening FFmpeg ``sendcmd``
updates from ``x``-only to ``w/h/x/y`` centered on the tracked crop box.

Supports both audio-energy beat detection (``emphasis_times``) and editorial
transcript hook/punchline beats (``merge_emphasis_times``) while guaranteeing
overlapping pushes take ``max()`` rather than compounding.
"""

from __future__ import annotations

import os
from typing import Sequence

import numpy as np

MAX_ZOOM: float = float(os.environ.get("PUNCH_IN_ZOOM", "1.12"))
RISE_SECONDS: float = 0.25
HOLD_SECONDS: float = 1.30
FALL_SECONDS: float = 0.55
BEAT_WINDOW: float = 0.2
MIN_GAP_SECONDS: float = 18.0
BEAT_PROMINENCE: float = 0.60


def _ease(t: float) -> float:
    """Smoothstep on ``[0, 1]``."""
    t = min(max(float(t), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def zoom_curve(
    n_frames: int,
    fps: float,
    emphasis_times: Sequence[float],
    max_zoom: float | None = None,
    start_offset: float = 0.0,
) -> list[float]:
    """Return per-frame zoom factors (``1.0`` = unzoomed) for one scene."""
    peak = MAX_ZOOM if max_zoom is None else float(max_zoom)
    zooms = [1.0] * max(0, int(n_frames))
    if not zooms or peak <= 1.0 or fps <= 0:
        return zooms

    span = RISE_SECONDS + HOLD_SECONDS + FALL_SECONDS
    for t in emphasis_times:
        local = float(t) - float(start_offset)
        if local <= -span or local >= n_frames / float(fps):
            continue
        f_start = max(0, int(local * fps))
        f_end = min(n_frames, int((local + span) * fps) + 1)
        for f in range(f_start, f_end):
            dt = f / float(fps) - local
            if dt < 0:
                continue
            if dt < RISE_SECONDS:
                amount = _ease(dt / RISE_SECONDS)
            elif dt < RISE_SECONDS + HOLD_SECONDS:
                amount = 1.0
            elif dt < span:
                amount = 1.0 - _ease((dt - RISE_SECONDS - HOLD_SECONDS) / FALL_SECONDS)
            else:
                continue
            zooms[f] = max(zooms[f], 1.0 + (peak - 1.0) * amount)
    return zooms


def crop_boxes(
    xs: Sequence[int],
    zooms: Sequence[float],
    crop_w: int,
    crop_h: int,
    orig_w: int,
    orig_h: int,
) -> list[tuple[int, int, int, int]]:
    """Return even-aligned ``(w, h, x, y)`` per frame centered on the tracked crop."""
    boxes: list[tuple[int, int, int, int]] = []
    for i, x in enumerate(xs):
        z = zooms[i] if i < len(zooms) else 1.0
        z = max(1.0, float(z))
        w = int(crop_w / z)
        h = int(crop_h / z)
        w -= w % 2
        h -= h % 2
        w = max(2, min(w, orig_w))
        h = max(2, min(h, orig_h))

        cx = float(x) + crop_w / 2.0
        cy = crop_h / 2.0
        nx = int(round(cx - w / 2.0))
        ny = int(round(cy - h / 2.0))
        nx = max(0, min(nx, orig_w - w))
        ny = max(0, min(ny, orig_h - h))
        boxes.append((w, h, nx - (nx % 2), ny - (ny % 2)))
    return boxes


def sendcmd_lines(
    boxes: Sequence[tuple[int, int, int, int]],
    fps: float,
    target: str = "crop@c",
) -> list[str]:
    """Emit change-point-deduped FFmpeg ``sendcmd`` lines for ``w/h/x/y``."""
    lines: list[str] = []
    prev: tuple[int, int, int, int] | None = None
    for i, box in enumerate(boxes):
        if box == prev:
            continue
        t = i / float(fps)
        w, h, x, y = box
        pw, ph, px, py = prev if prev is not None else (None, None, None, None)
        if w != pw:
            lines.append(f"{t:.4f} {target} w {w};")
        if h != ph:
            lines.append(f"{t:.4f} {target} h {h};")
        if x != px:
            lines.append(f"{t:.4f} {target} x {x};")
        if y != py:
            lines.append(f"{t:.4f} {target} y {y};")
        prev = box
    return lines


def emphasis_times(
    video_path: str,
    duration: float,
    window: float = BEAT_WINDOW,
    min_gap: float = MIN_GAP_SECONDS,
    prominence: float = BEAT_PROMINENCE,
) -> list[float]:
    """Detect clip-relative emphasis timestamps (seconds) from audio RMS peaks."""
    from lib.active_speaker import audio_envelope

    envelope = audio_envelope(video_path, 0.0, duration, window_s=window)
    if not envelope:
        return []

    values = np.asarray(envelope, dtype=float)
    baseline = float(np.median(values))
    peak = float(values.max())
    if peak - baseline <= 1e-6:
        return []

    threshold = baseline + (peak - baseline) * float(prominence)
    times: list[float] = []
    last = -1e9
    for i, v in enumerate(values):
        t = i * float(window)
        if float(v) >= threshold and (t - last) >= float(min_gap):
            times.append(round(t, 3))
            last = t
    return times


def merge_emphasis_times(
    audio_beats: Sequence[float] | None,
    editorial_beats: Sequence[float] | None = None,
    *,
    min_gap: float = MIN_GAP_SECONDS,
) -> list[float]:
    """Combine editorial transcript hook/punchline beats with audio beats.

    Editorial beats take priority: they are accepted first (deduped by
    ``min_gap``), and audio beats fill remaining open gaps without crowding
    within ``min_gap`` seconds of any editorial beat.
    """
    accepted: list[float] = []

    def _try_add(raw_t: float) -> None:
        t = round(float(raw_t), 3)
        if t < 0:
            return
        if all(abs(t - existing) >= float(min_gap) for existing in accepted):
            accepted.append(t)

    for t in sorted(float(v) for v in (editorial_beats or [])):
        _try_add(t)
    for t in sorted(float(v) for v in (audio_beats or [])):
        _try_add(t)

    accepted.sort()
    return accepted
