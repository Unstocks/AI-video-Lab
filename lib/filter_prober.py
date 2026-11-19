"""FFmpeg filter and codec hardware capability discovery."""

from __future__ import annotations

import logging
import subprocess
import threading
from typing import NamedTuple

logger = logging.getLogger(__name__)


class Capabilities(NamedTuple):
    has_cas: bool
    has_unsharp: bool
    has_hqdn3d: bool
    has_hevc_nvenc: bool
    has_h264_nvenc: bool


class CapabilityProber:
    """Thread-safe cached prober for FFmpeg filters and hardware codecs."""

    def __init__(self, ffmpeg_bin: str = "ffmpeg") -> None:
        self.ffmpeg = ffmpeg_bin
        self._caps: Capabilities | None = None
        self._lock = threading.Lock()

    def probe(self) -> Capabilities:
        with self._lock:
            if self._caps is not None:
                return self._caps

            has_cas = self._check_filter("cas")
            has_unsharp = self._check_filter("unsharp")
            has_hqdn3d = self._check_filter("hqdn3d")
            has_hevc_nvenc = self._check_encoder("hevc_nvenc")
            has_h264_nvenc = self._check_encoder("h264_nvenc")

            self._caps = Capabilities(
                has_cas=has_cas,
                has_unsharp=has_unsharp,
                has_hqdn3d=has_hqdn3d,
                has_hevc_nvenc=has_hevc_nvenc,
                has_h264_nvenc=has_h264_nvenc,
            )
            logger.info("Probed FFmpeg Capabilities: %s", self._caps)
            return self._caps

    def reset_cache(self) -> None:
        """Reset cached capabilities (useful in unit testing)."""
        with self._lock:
            self._caps = None

    def _check_filter(self, filter_name: str) -> bool:
        try:
            res = subprocess.run(
                [self.ffmpeg, "-hide_banner", "-filters"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            # Lines format: ' ... filter_name ... Description'
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] == filter_name:
                    return True
        except Exception:
            pass
        return False

    def _check_encoder(self, codec_name: str) -> bool:
        cmd = [
            self.ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
            "-c:v", codec_name, "-f", "null", "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
            return res.returncode == 0
        except Exception:
            return False


GLOBAL_PROBER = CapabilityProber()
