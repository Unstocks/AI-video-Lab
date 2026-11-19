"""Unit tests for Multi-Resolution Ladder profiles in lib/media_profiles.py and lib/ffmpeg_profiles.py."""

from __future__ import annotations

import pytest

from lib.media_profiles import (
    ALL_PROFILES,
    AspectRatio,
    YOUTUBE_SHORTS_1080P,
    YOUTUBE_SHORTS_1440P,
    YOUTUBE_SHORTS_4K,
    get_profile,
)
from lib.ffmpeg_profiles import (
    COLOR_METADATA_BT709,
    build_clarity_filtergraph,
    export_encode_args,
    nvenc_hevc_available,
)


def test_vertical_ladder_profiles_registered():
    p1080 = get_profile("youtube_shorts_1080p")
    assert p1080.width == 1080
    assert p1080.height == 1920
    assert p1080.aspect_ratio == AspectRatio.PORTRAIT_9_16

    p1440 = get_profile("youtube_shorts_1440p")
    assert p1440.width == 1440
    assert p1440.height == 2560
    assert p1440.aspect_ratio == AspectRatio.PORTRAIT_9_16

    p4k = get_profile("youtube_shorts_4k")
    assert p4k.width == 2160
    assert p4k.height == 3840
    assert p4k.aspect_ratio == AspectRatio.PORTRAIT_9_16


def test_build_clarity_filtergraph():
    # 0% returns empty list (bypass)
    assert build_clarity_filtergraph(0) == []

    # 45% builds hqdn3d and cas
    chain = build_clarity_filtergraph(45)
    assert len(chain) == 1
    assert "hqdn3d=" in chain[0]
    assert "cas=strength=" in chain[0]


def test_export_encode_args_hevc_tags():
    args = export_encode_args("1440p", codec="hevc")
    # Must contain Rec.709 color tags
    for tag in COLOR_METADATA_BT709:
        assert tag in args

    if nvenc_hevc_available():
        assert "-tag:v" in args
        tag_idx = args.index("-tag:v")
        assert args[tag_idx + 1] == "hvc1"
        assert "hevc_nvenc" in args
