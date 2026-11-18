"""Central FFmpeg video/audio encoding, loudness, metadata-scrub, and filter helpers.

Provides automatic NVIDIA NVENC detection with deterministic ``libx264`` fallback,
explicit ``yuv420p`` output pixel format, single-pass broadcast loudness
normalization (``-14 LUFS``, ``-2.0 dBTP`` true-peak headroom for AAC), container
metadata scrubbing, and fast quarter-resolution blurred backdrop generation.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Literal

from lib.ffmpeg_utils import escape_ffmpeg_filter_path

logger = logging.getLogger(__name__)

QUALITY = "quality"
QUALITY_FAST = "quality_fast"
DELIVERY = "delivery"
INTERMEDIATE = "intermediate"

_X264_PRESETS: dict[str, tuple[str, int]] = {
    QUALITY: ("medium", 18),
    QUALITY_FAST: ("fast", 18),
    DELIVERY: ("fast", 22),
    INTERMEDIATE: ("fast", 18),
}

# NVENC -cq ≈ x264 CRF + 7; -pix_fmt yuv420p is mandatory so browsers never see gbrp.
_NVENC_ARGS: dict[str, tuple[str, ...]] = {
    QUALITY: (
        "-c:v", "h264_nvenc", "-preset", "p3", "-tune", "hq",
        "-rc", "vbr", "-cq", "25", "-b:v", "0",
        "-spatial-aq", "1", "-temporal-aq", "1", "-pix_fmt", "yuv420p",
    ),
    QUALITY_FAST: (
        "-c:v", "h264_nvenc", "-preset", "p3", "-tune", "hq",
        "-rc", "vbr", "-cq", "25", "-b:v", "0",
        "-spatial-aq", "1", "-pix_fmt", "yuv420p",
    ),
    DELIVERY: (
        "-c:v", "h264_nvenc", "-preset", "p3",
        "-rc", "vbr", "-cq", "29", "-b:v", "0",
        "-spatial-aq", "1", "-pix_fmt", "yuv420p",
    ),
    INTERMEDIATE: (
        "-c:v", "h264_nvenc", "-preset", "p1",
        "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p",
    ),
}

# Strips source container & stream handler metadata (e.g. YouTube handler tags).
METADATA_SCRUB: tuple[str, ...] = (
    "-map_metadata", "-1",
    "-map_chapters", "-1",
    "-map_metadata:s:v", "-1",
    "-map_metadata:s:a", "-1",
)

# -14 LUFS matches Shorts/Reels/TikTok playback targets; -2.0 dBTP leaves headroom
# for AAC inter-sample peaks so delivered clips do not clip above -1.0 dBTP.
LOUDNORM_FILTER: str = "loudnorm=I=-14:TP=-2.0:LRA=11"

_probe_lock = threading.Lock()
_nvenc_ok: bool | None = None


def _probe_nvenc() -> bool:
    """Run a tiny 256x256 lavfi encode to confirm h264_nvenc works end-to-end."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
        "-c:v", "h264_nvenc", "-pix_fmt", "yuv420p", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return proc.returncode == 0
    except Exception:
        return False


def nvenc_available() -> bool:
    """Probe h264_nvenc once and cache the result thread-safely."""
    global _nvenc_ok
    if _nvenc_ok is None:
        with _probe_lock:
            if _nvenc_ok is None:
                _nvenc_ok = _probe_nvenc()
    return _nvenc_ok


def reset_encoder_cache() -> None:
    """Test hook: clear cached NVENC probe status."""
    global _nvenc_ok
    with _probe_lock:
        _nvenc_ok = None


def resolve_video_codec(requested: str = "auto") -> Literal["h264_nvenc", "libx264"] | str:
    """Resolve ``requested`` codec against hardware availability and env overrides."""
    mode = (requested or "auto").strip().lower()
    env_override = os.environ.get("AI_VIDEO_LAB_ENCODER", "").strip().lower()
    if mode == "auto" and env_override in ("x264", "libx264", "nvenc", "h264_nvenc"):
        mode = "libx264" if env_override in ("x264", "libx264") else "h264_nvenc"

    if mode in ("auto", "nvenc", "h264_nvenc"):
        if nvenc_available():
            return "h264_nvenc"
        if mode in ("nvenc", "h264_nvenc"):
            logger.warning("h264_nvenc requested but unavailable; falling back to libx264")
        return "libx264"
    if mode in ("x264", "libx264"):
        return "libx264"
    return requested.strip()


def video_encode_args(
    tier: str = QUALITY,
    *,
    codec: str = "auto",
    crf: int | None = None,
) -> list[str]:
    """Return FFmpeg video codec & quality arguments for ``tier`` and ``codec``."""
    if tier not in _X264_PRESETS:
        raise ValueError(f"Unknown encode tier: {tier!r}")
    resolved = resolve_video_codec(codec)
    if resolved == "h264_nvenc":
        args = list(_NVENC_ARGS[tier])
        if crf is not None and tier != INTERMEDIATE:
            # Map x264 CRF into equivalent NVENC VBR CQ ballpark (clamped 1..51).
            cq = max(1, min(51, int(crf) + 7))
            cq_idx = args.index("-cq") + 1
            args[cq_idx] = str(cq)
        return args
    if resolved == "libx264":
        preset, default_crf = _X264_PRESETS[tier]
        effective_crf = default_crf if crf is None else int(crf)
        return [
            "-c:v", "libx264", "-preset", preset,
            "-crf", str(effective_crf), "-pix_fmt", "yuv420p",
        ]
    if resolved.lower() == "copy":
        return ["-c:v", "copy"]
    # Explicit non-H.264 codec passthrough (e.g. libvpx-vp9).
    effective_crf = _X264_PRESETS[tier][1] if crf is None else int(crf)
    return ["-c:v", resolved, "-crf", str(effective_crf), "-pix_fmt", "yuv420p"]


def audio_encode_args(
    *,
    normalize: bool = True,
    bitrate: str = "192k",
    sample_rate: int = 48000,
) -> list[str]:
    """Return FFmpeg AAC audio encode arguments with optional -14 LUFS loudnorm.

    Explicitly pins ``-ar 48000`` because FFmpeg's ``loudnorm`` filter internally
    upsamples to 192 kHz / 96 kHz unless resampled back down for AAC delivery.
    """
    env_enabled = os.environ.get("AI_VIDEO_LAB_AUDIO_NORMALIZE", "1").strip() != "0"
    args: list[str] = []
    if normalize and env_enabled:
        args.extend(["-af", LOUDNORM_FILTER])
    args.extend(["-c:a", "aac", "-b:a", bitrate, "-ar", str(sample_rate)])
    return args


def blurred_backdrop(out_w: int, out_h: int, sigma: float = 12.0) -> str:
    """Quarter-resolution gblur backdrop filter chain (~45% less CPU, SSIM >= 0.994)."""
    small_w = max(2, (out_w // 4) - ((out_w // 4) % 2))
    small_h = max(2, (out_h // 4) - ((out_h // 4) % 2))
    return (
        f"scale=-2:{small_h},crop=w=min(iw\\,{small_w}):h={small_h},"
        f"gblur=sigma={sigma / 4.0:g},scale={out_w}:{out_h}"
    )


def escape_filter_value(value: str | Path) -> str:
    """Escape a filesystem path for use inside a quoted FFmpeg filtergraph value."""
    return escape_ffmpeg_filter_path(value)
