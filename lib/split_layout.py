"""2-speaker vertical SPLIT layout analysis and FFmpeg filtergraph geometry.

Pure NumPy for all analysis/geometry functions so unit tests run offline
without FFmpeg/OpenCV. Handles:
- IoU face deduplication (``MAX_FACE_OVERLAP = 0.30``)
- Two-shot coexistence & horizontal separation verification
- Outlier-proof median face centers ``(cx, cy, w, h)``
- Headroom-biased half-frame crop geometry (``y = round(cy - crop_h * 0.42)``)
- Exact even-dimension ``vstack + pad`` FFmpeg filtergraph (left speaker on top)
"""

from __future__ import annotations

import os
from typing import Any, Sequence

import numpy as np

MIN_COEXISTENCE: float = 0.50
MIN_SEPARATION: float = 0.20
MIN_FACE_WIDTH: float = 0.045
MIN_SCENE_SECONDS: float = 2.5
SPLIT_TIGHTNESS: float = float(os.environ.get("SPLIT_TIGHTNESS", "0.80"))
MAX_FACE_OVERLAP: float = 0.30

SECONDS_PER_SAMPLE: float = 1.5
MIN_SAMPLES: int = 8
MAX_SAMPLES: int = 24


def _iou(a: Sequence[float], b: Sequence[float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def dedupe_faces(
    candidates: Sequence[dict[str, Any]],
    threshold: float = MAX_FACE_OVERLAP,
) -> list[dict[str, Any]]:
    """Drop duplicate detections of the same face, keeping the largest box."""
    kept: list[dict[str, Any]] = []
    ordered = sorted(
        candidates,
        key=lambda c: float(c["box"][2]) * float(c["box"][3]),
        reverse=True,
    )
    for cand in ordered:
        if all(_iou(cand["box"], k["box"]) <= threshold for k in kept):
            kept.append(cand)
    return kept


def _two_largest(
    candidates: Sequence[dict[str, Any]],
    frame_w: float,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    big = [
        c
        for c in dedupe_faces(candidates)
        if float(c["box"][2]) >= MIN_FACE_WIDTH * float(frame_w)
    ]
    if len(big) < 2:
        return None
    big.sort(
        key=lambda c: float(c.get("score") or (c["box"][2] * c["box"][3])),
        reverse=True,
    )
    a, b = big[0], big[1]
    left, right = sorted((a, b), key=lambda c: float(c["box"][0]))
    return left, right


def _centre(box: Sequence[float]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return float(x) + float(w) / 2.0, float(y) + float(h) / 2.0, float(w), float(h)


def as_box(centre: Sequence[float]) -> list[float]:
    """Convert ``(cx, cy, w, h)`` centre tuple back to ``[x, y, w, h]`` box."""
    cx, cy, w, h = centre
    return [float(cx) - float(w) / 2.0, float(cy) - float(h) / 2.0, float(w), float(h)]


def analyze_scene(
    frames: Sequence[Sequence[dict[str, Any]]],
    frame_w: float,
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]] | None:
    """Return median ``(left, right)`` ``(cx, cy, w, h)`` if frames show a valid two-shot."""
    if not frames or frame_w <= 0:
        return None

    lefts: list[tuple[float, float, float, float]] = []
    rights: list[tuple[float, float, float, float]] = []
    for candidates in frames:
        pair = _two_largest(candidates, frame_w)
        if not pair:
            continue
        left_c, right_c = _centre(pair[0]["box"]), _centre(pair[1]["box"])
        if (right_c[0] - left_c[0]) < MIN_SEPARATION * float(frame_w):
            continue
        lefts.append(left_c)
        rights.append(right_c)

    if len(lefts) < MIN_COEXISTENCE * len(frames):
        return None

    left = tuple(float(np.median([c[i] for c in lefts])) for i in range(4))
    right = tuple(float(np.median([c[i] for c in rights])) for i in range(4))
    return left, right  # type: ignore[return-value]


def split_geometry(
    orig_w: int,
    orig_h: int,
    out_w: int,
    out_h: int,
    centre: Sequence[float],
    *,
    tightness: float | None = None,
) -> tuple[int, int, int, int, int]:
    """Return even-aligned ``(crop_w, crop_h, x, y, half_h)`` framing ``centre``."""
    half_h = out_h // 2
    half_h -= half_h % 2
    aspect = out_w / float(half_h)

    eff_tightness = SPLIT_TIGHTNESS if tightness is None else float(tightness)
    crop_h = int(round(orig_h * max(0.3, min(eff_tightness, 1.0))))
    crop_w = int(round(crop_h * aspect))
    if crop_w > orig_w:
        crop_w = orig_w
        crop_h = int(round(crop_w / aspect))

    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    cx, cy = float(centre[0]), float(centre[1])
    x = int(round(cx - crop_w / 2.0))
    x = max(0, min(x, orig_w - crop_w))

    # Headroom bias: place face center at 42% down from crop top
    y = int(round(cy - crop_h * 0.42))
    y = max(0, min(y, orig_h - crop_h))

    return crop_w, crop_h, x - (x % 2), y - (y % 2), half_h


def split_filtergraph(
    orig_w: int,
    orig_h: int,
    out_w: int,
    out_h: int,
    left_centre: Sequence[float],
    right_centre: Sequence[float],
    *,
    tightness: float | None = None,
) -> str:
    """Build FFmpeg ``vstack + pad`` filtergraph placing left speaker on top."""
    top_w, top_h, top_x, top_y, half_h = split_geometry(
        orig_w, orig_h, out_w, out_h, left_centre, tightness=tightness
    )
    bot_w, bot_h, bot_x, bot_y, _ = split_geometry(
        orig_w, orig_h, out_w, out_h, right_centre, tightness=tightness
    )
    return (
        f"[0:v]split=2[ta][ba];"
        f"[ta]crop=w={top_w}:h={top_h}:x={top_x}:y={top_y},"
        f"scale={out_w}:{half_h}[top];"
        f"[ba]crop=w={bot_w}:h={bot_h}:x={bot_x}:y={bot_y},"
        f"scale={out_w}:{half_h}[bot];"
        f"[top][bot]vstack=inputs=2,"
        f"pad={out_w}:{out_h}:0:0,setsar=1[v]"
    )


def detect_split_scenes(
    video_path: str,
    scene_boundaries: Sequence[tuple[int, int]],
    strategies: Sequence[str],
    *,
    fps: float,
    detector: Any,
    samples: int | None = None,
) -> dict[int, tuple[tuple[float, float, float, float], tuple[float, float, float, float]]]:
    """Identify qualifying ``GENERAL`` scenes that contain two coexisting speakers.

    Returns ``{scene_index: (left_centre, right_centre)}``.
    """
    import cv2
    from lib.face_detector import read_frames_at

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {}

    eff_fps = float(fps) if fps and fps > 0 else (cap.get(cv2.CAP_PROP_FPS) or 30.0)
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    found: dict[int, tuple[tuple[float, float, float, float], tuple[float, float, float, float]]] = {}
    plan: list[tuple[int, int, list[int]]] = []

    try:
        for i, (s_f, e_f) in enumerate(scene_boundaries):
            if i < len(strategies) and strategies[i] != "GENERAL":
                continue
            duration = (e_f - s_f) / eff_fps
            if duration < MIN_SCENE_SECONDS:
                continue
            n = (
                int(samples)
                if samples is not None
                else int(min(max(duration / SECONDS_PER_SAMPLE, MIN_SAMPLES), MAX_SAMPLES))
            )
            last_f = e_f - 1
            if total_frames > 0:
                last_f = min(last_f, total_frames - 1)
            if last_f < s_f:
                continue
            idxs = [int(round(f)) for f in np.linspace(s_f, last_f, n)]
            plan.append((i, n, idxs))

        if not plan:
            return {}

        flat = [f_idx for _i, _n, idxs in plan for f_idx in idxs]
        frames_iter = read_frames_at(cap, flat)
        for i, n, idxs in plan:
            sampled: list[list[dict[str, Any]]] = []
            for _f_idx in idxs:
                frame = next(frames_iter, None)
                if frame is None:
                    continue
                if float(frame.mean()) < 16.0:
                    continue
                sampled.append(detector.detect(frame))
            if len(sampled) < max(4, n // 2):
                continue
            pair = analyze_scene(sampled, frame_w)
            if pair:
                found[i] = pair
    finally:
        cap.release()

    return found
