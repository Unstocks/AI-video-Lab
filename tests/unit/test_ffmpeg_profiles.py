"""Unit and real-FFmpeg tests for lib.ffmpeg_profiles."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from lib import ffmpeg_profiles
from lib.ffmpeg_profiles import (
    DELIVERY,
    INTERMEDIATE,
    LOUDNORM_FILTER,
    METADATA_SCRUB,
    QUALITY,
    QUALITY_FAST,
    audio_encode_args,
    blurred_backdrop,
    escape_filter_value,
    reset_encoder_cache,
    resolve_video_codec,
    video_encode_args,
)


class TestProfilesUnit:
    def test_profiles_are_defined_and_distinct(self):
        assert {QUALITY, QUALITY_FAST, DELIVERY, INTERMEDIATE} == {
            "quality", "quality_fast", "delivery", "intermediate"
        }
        assert LOUDNORM_FILTER == "loudnorm=I=-14:TP=-2.0:LRA=11"
        assert "-map_metadata" in METADATA_SCRUB and "-1" in METADATA_SCRUB

    def test_video_encode_args_libx264(self):
        args = video_encode_args(QUALITY, codec="libx264")
        assert args[:2] == ["-c:v", "libx264"]
        assert "-crf" in args and "18" in args
        assert "-preset" in args and "medium" in args
        assert "-pix_fmt" in args and "yuv420p" in args

    def test_video_encode_args_nvenc(self):
        with patch.object(ffmpeg_profiles, "nvenc_available", return_value=True):
            args = video_encode_args(QUALITY_FAST, codec="h264_nvenc")
        assert args[:2] == ["-c:v", "h264_nvenc"]
        assert "-rc" in args and "vbr" in args
        assert "-cq" in args and "25" in args
        assert "-crf" not in args
        assert "-pix_fmt" in args and "yuv420p" in args

    def test_resolve_video_codec_auto_uses_nvenc_probe(self):
        reset_encoder_cache()
        with patch.object(ffmpeg_profiles, "nvenc_available", return_value=True):
            assert resolve_video_codec("auto") == "h264_nvenc"
            assert resolve_video_codec("h264_nvenc") == "h264_nvenc"
            assert resolve_video_codec("libx264") == "libx264"
        with patch.object(ffmpeg_profiles, "nvenc_available", return_value=False):
            assert resolve_video_codec("auto") == "libx264"
            assert resolve_video_codec("h264_nvenc") == "libx264"

    def test_audio_encode_args(self):
        plain = audio_encode_args(normalize=False)
        assert plain == ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]

        norm = audio_encode_args(normalize=True, bitrate="160k")
        assert "-af" in norm
        assert LOUDNORM_FILTER in norm
        assert "-ar" in norm and "48000" in norm
        assert "160k" in norm

    def test_blurred_backdrop_quarter_res_dimensions(self):
        f = blurred_backdrop(1080, 1920, sigma=12.0)
        assert "scale=-2:480" in f
        assert "crop=w=min(iw\\,270):h=480" in f
        assert "gblur=sigma=3" in f
        assert "scale=1080:1920" in f

    def test_escape_filter_value(self):
        escaped = escape_filter_value(r"C:\AI-Video-Lab\clip's:1.ass")
        assert "\\:" in escaped
        assert "\\'" in escaped


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe unavailable")
class TestProfilesRealFfmpeg:
    def test_real_encode_metadata_scrub_and_loudnorm(self, tmp_path: Path):
        """Verify live FFmpeg encode (NVENC if present, else x264), metadata scrub, 48 kHz AAC, and -14 LUFS."""
        reset_encoder_cache()
        src = tmp_path / "src_tagged.mp4"
        out = tmp_path / "out_broadcast.mp4"

        # 1. Create a 3-second test video with loud audio (-3 dBFS sine) + custom metadata tags
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=3",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3",
                "-af", "volume=-3dB",
                "-metadata", "title=LEAKED_INTERNAL_TITLE",
                "-metadata", "comment=SECRET_TAG",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        # 2. Encode through our unified ffmpeg_profiles helpers
        codec = resolve_video_codec("auto")
        cmd = [
            "ffmpeg", "-y",
            "-i", str(src),
            *video_encode_args(QUALITY, codec=codec),
            *audio_encode_args(normalize=True),
            *METADATA_SCRUB,
            "-movflags", "+faststart",
            str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, f"FFmpeg failed ({codec}): {proc.stderr}"
        assert out.is_file() and out.stat().st_size > 1024

        # 3. Probe output: h264 + yuv420p + 48000 Hz AAC + scrubbed source metadata
        probe = json.loads(
            subprocess.check_output(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(out)],
                text=True,
                timeout=15,
            )
        )
        v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
        assert v_stream["codec_name"] == "h264"
        assert v_stream["pix_fmt"] == "yuv420p"
        assert a_stream["codec_name"] == "aac"
        assert int(a_stream["sample_rate"]) == 48000

        fmt_tags = {k.lower(): v for k, v in probe.get("format", {}).get("tags", {}).items()}
        assert "title" not in fmt_tags
        assert "comment" not in fmt_tags

        # 4. Measure integrated loudness via ebur128 (target -14 LUFS +/- 2.5 LU for 3s sine)
        ebur = subprocess.run(
            ["ffmpeg", "-i", str(out), "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert ebur.returncode == 0
        summary_idx = ebur.stderr.rfind("Summary:")
        summary = ebur.stderr[summary_idx:] if summary_idx != -1 else ebur.stderr
        m_i = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", summary)
        m_tp = re.search(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", summary)
        assert m_i is not None, ebur.stderr
        lufs = float(m_i.group(1))
        assert -16.5 <= lufs <= -11.5, f"Unexpected loudness: {lufs} LUFS"
        if m_tp:
            assert float(m_tp.group(1)) <= -1.0, f"Peak too hot: {m_tp.group(1)} dBFS"
