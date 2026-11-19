"""CFR normalization and sample-accurate A/V sync drift validation."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import NamedTuple

from lib.filter_prober import GLOBAL_PROBER

logger = logging.getLogger(__name__)


class ConformanceResult(NamedTuple):
    is_cfr: bool
    av_sync_drift_seconds: float
    passed_sync_gate: bool
    details: dict[str, str | float]


def validate_cfr_and_sync(
    video_path: Path,
    max_allowed_drift_seconds: float = 0.05,
    ffprobe_bin: str = "ffprobe",
) -> ConformanceResult:
    """Verify constant frame rate and A/V stream alignment via ffprobe."""
    cmd = [
        ffprobe_bin, "-v", "error",
        "-show_streams", "-show_format",
        "-of", "json",
        str(video_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise ValueError(f"ffprobe failed on {video_path}: {res.stderr}")

    info = json.loads(res.stdout)
    streams = info.get("streams", [])
    v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not v_stream:
        raise ValueError("No video stream found")

    # CFR check: avg_frame_rate == r_frame_rate
    avg_fps = v_stream.get("avg_frame_rate", "")
    r_fps = v_stream.get("r_frame_rate", "")
    is_cfr = (avg_fps == r_fps) and bool(avg_fps) and avg_fps != "0/0"

    v_duration = float(v_stream.get("duration") or info.get("format", {}).get("duration", 0.0))
    a_duration = float(a_stream.get("duration", v_duration)) if a_stream else v_duration
    drift = abs(v_duration - a_duration)

    passed = (drift <= max_allowed_drift_seconds) and is_cfr
    return ConformanceResult(
        is_cfr=is_cfr,
        av_sync_drift_seconds=drift,
        passed_sync_gate=passed,
        details={
            "avg_fps": avg_fps,
            "r_fps": r_fps,
            "video_duration": v_duration,
            "audio_duration": a_duration,
            "drift_seconds": drift,
        },
    )


def normalize_to_cfr_proxy(
    master_path: Path,
    proxy_output_path: Path,
    target_fps: int = 30,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """Normalize variable frame rate input to a strict CFR 720p proxy."""
    caps = GLOBAL_PROBER.probe()
    codec = "h264_nvenc" if caps.has_h264_nvenc else "libx264"
    cmd = [
        ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(master_path),
        "-vf", f"scale=-2:720,fps=fps={target_fps}:round=near,setpts=PTS-STARTPTS,format=yuv420p",
        "-af", "aresample=async=1000:first_pts=0,asetpts=PTS-STARTPTS",
        "-c:v", codec,
        "-preset", "p1" if codec == "h264_nvenc" else "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(proxy_output_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"CFR proxy generation failed: {res.stderr}")

    return proxy_output_path
