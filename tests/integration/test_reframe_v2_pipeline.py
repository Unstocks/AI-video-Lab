"""Integration & helper tests for Smart Reframe v2 (lib.reframe_v2 + AutoReframe)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lib import layout_ranges
from lib.reframe_v2 import (
    apply_crop_overrides,
    dedupe_sendcmd_lines,
    delivery_size,
    general_filtergraph,
    source_already_fits,
)
from tools.analysis.scene_detect import _merge_short_scenes
from tools.video.auto_reframe import AutoReframe


class TestReframeV2PureHelpers:
    def test_delivery_size_enforces_1080_floor_and_even_dims(self):
        # 720p landscape -> 1080x1920 delivery floor
        assert delivery_size(1280, 720, 9 / 16) == (1080, 1920)
        # 1080p landscape -> 1080x1920 delivery floor
        assert delivery_size(1920, 1080, 9 / 16) == (1080, 1920)
        # 4K landscape -> preserves 1216x2160 (never downscales!)
        w, h = delivery_size(3840, 2160, 9 / 16)
        assert w >= 1080 and w % 2 == 0 and h % 2 == 0

    def test_source_already_fits_vertical_vs_landscape(self):
        assert source_already_fits(1080, 1920, 9 / 16) is True
        assert source_already_fits(720, 1280, 9 / 16) is True
        assert source_already_fits(1920, 1080, 9 / 16) is False

    def test_merge_short_scenes_absorbs_flash_cuts(self):
        bounds = [(0, 5), (5, 90), (90, 96), (96, 180)]  # @30fps: 0.17s lead, 0.20s flash
        merged = _merge_short_scenes(bounds, fps=30.0, min_sec=0.4)
        assert merged == [(0, 96), (96, 180)]

    def test_apply_crop_overrides_supports_single_and_split_and_wins_last(self):
        xs: list[int | None] = [500] * 60
        strategies = ["GENERAL", "TRACK"]
        bounds = [(0, 30), (30, 60)]
        splits: dict = {}

        apply_crop_overrides(
            xs,
            strategies,
            bounds,
            overrides={
                "0": 0.25,  # force TRACK left
                "1": {"top": {"x": 0.25, "y": 0.4}, "bottom": {"x": 0.75, "y": 0.4}},
                "99": 0.5,  # stale index ignored safely
            },
            crop_w=606,
            orig_w=1920,
            orig_h=1080,
            splits=splits,
        )
        assert strategies == ["TRACK", "SPLIT"]
        assert all(x == 177 for x in xs[:30])
        assert 30 in splits
        assert abs(splits[30][0][0] - 480.0) < 1.0
        assert abs(splits[30][1][0] - 1440.0) < 1.0

    def test_general_filtergraph_has_quarter_res_blur_and_42pct_floor(self):
        fg = general_filtergraph(1080, 1920, orig_w=1920, orig_h=1080)
        assert "scale=-2:480" in fg
        assert "gblur=sigma=3" in fg
        assert "scale=-2:806" in fg  # 42% of 1920 = 806px

    def test_dedupe_sendcmd_lines_only_emits_changes(self):
        lines = dedupe_sendcmd_lines([100, 100, 100, 120, 120], fps=30.0)
        assert len(lines) == 2
        assert lines[0].startswith("0.0000 crop@c x 100;")
        assert lines[1].startswith("0.1000 crop@c x 120;")


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
class TestReframeV2RealFfmpeg:
    def test_multi_scene_reframe_v2_with_split_override_and_punch_in(self, tmp_path: Path):
        """Render a 4-second synthetic 16:9 clip through AutoReframe(layout_mode='auto')
        with 2 scenes (scene 0: TRACK + punch-in, scene 1: SPLIT override) and verify
        1080x1920 H.264 yuv420p output + valid .layout.json sidecar.
        """
        src = tmp_path / "podcast_16x9.mp4"
        out = tmp_path / "clip_9x16.mp4"

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )

        tool = AutoReframe()
        res = tool.execute({
            "input_path": str(src),
            "output_path": str(out),
            "layout_mode": "auto",
            "shot_cuts": [2.0],
            "enable_punch_in": True,
            "emphasis_times": [0.5],
            "crop_overrides": {
                "0": 0.30,
                "1": {"top": {"x": 0.25, "y": 0.45}, "bottom": {"x": 0.75, "y": 0.45}},
            },
            "codec": "auto",
            "audio_copy": True,
            "scrub_metadata": True,
        })
        assert res.success, res.error
        assert out.is_file() and out.stat().st_size > 2048

        probe = json.loads(
            subprocess.check_output(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(out)],
                text=True,
                timeout=15,
            )
        )
        v = next(s for s in probe["streams"] if s["codec_type"] == "video")
        a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
        assert int(v["width"]) == 1080 and int(v["height"]) == 1920
        assert v["codec_name"] == "h264"
        assert v["pix_fmt"] == "yuv420p"
        assert a["codec_name"] == "aac"

        payload = layout_ranges.read_payload(out)
        assert [r["layout"] for r in payload["ranges"]] == ["track", "split"]
        assert payload["punch_ins"] == [0.5]
        assert layout_ranges.split_ranges(payload["ranges"]) == [(2.0, 4.0)]

    def test_vertical_source_passthrough_never_pillarboxes(self, tmp_path: Path):
        src = tmp_path / "already_vertical.mp4"
        out = tmp_path / "passthrough.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(src),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        res = AutoReframe().execute({
            "input_path": str(src),
            "output_path": str(out),
            "layout_mode": "auto",
        })
        assert res.success, res.error
        assert res.data["method"] == "reframe_v2_passthrough"
        assert res.data["output_resolution"] == "1080x1920"
        assert layout_ranges.read(out)[0]["layout"] == "track"

