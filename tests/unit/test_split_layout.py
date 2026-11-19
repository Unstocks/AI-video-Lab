"""Unit tests for lib.split_layout (2-speaker stacked vertical split)."""

from __future__ import annotations

from lib.split_layout import (
    analyze_scene,
    as_box,
    dedupe_faces,
    split_filtergraph,
    split_geometry,
)


def _cand(x, y, w, h):
    return {"box": [x, y, w, h], "score": w * h}


def test_dedupe_faces_drops_overlapping_duplicate():
    big = _cand(200, 200, 150, 150)
    dup = _cand(210, 205, 130, 130)
    other = _cand(1200, 200, 140, 140)
    kept = dedupe_faces([dup, big, other])
    assert len(kept) == 2
    assert kept[0]["box"] == big["box"]
    assert kept[1]["box"] == other["box"]


def test_analyze_scene_accepts_coexisting_speakers_with_outlier_robust_median():
    # 6 of 10 frames have both speakers (>= 0.50 MIN_COEXISTENCE), one outlier frame
    two = [_cand(350, 250, 150, 160), _cand(1400, 260, 150, 160)]
    outlier = [_cand(50, 50, 150, 160), _cand(1750, 800, 150, 160)]
    one = [_cand(350, 250, 150, 160)]
    frames = [two, two, two, two, two, outlier, one, one, one, one]
    res = analyze_scene(frames, frame_w=1920)
    assert res is not None
    left, right = res
    # Left speaker on left, right speaker on right, median ignores outlier
    assert abs(left[0] - 425.0) < 1.0
    assert abs(right[0] - 1475.0) < 1.0
    assert as_box(left) == [350.0, 250.0, 150.0, 160.0]


def test_analyze_scene_rejects_close_or_tiny_or_alternating_faces():
    # Too close (< 0.20 * 1920 = 384px)
    close = [_cand(700, 250, 140, 140), _cand(900, 250, 140, 140)]
    assert analyze_scene([close] * 8, frame_w=1920) is None

    # Tiny background face (< 0.045 * 1920 = 86.4px)
    tiny = [_cand(300, 250, 140, 140), _cand(1400, 250, 40, 40)]
    assert analyze_scene([tiny] * 8, frame_w=1920) is None

    # Shot-reverse-shot: faces never coexist in same frame
    alternating = [[_cand(300, 250, 140, 140)], [_cand(1400, 250, 140, 140)]] * 5
    assert analyze_scene(alternating, frame_w=1920) is None


def test_split_geometry_even_dims_and_headroom_bias():
    crop_w, crop_h, x, y, half_h = split_geometry(1920, 1080, 1080, 1920, (425.0, 330.0))
    assert half_h == 960
    assert crop_w % 2 == 0 and crop_h % 2 == 0
    assert x % 2 == 0 and y % 2 == 0
    assert 0 <= x <= 1920 - crop_w
    assert 0 <= y <= 1080 - crop_h


def test_split_filtergraph_uses_vstack_and_pad():
    fg = split_filtergraph(1920, 1080, 1080, 1920, (425.0, 330.0), (1475.0, 330.0))
    assert "[top][bot]vstack=inputs=2,pad=1080:1920:0:0,setsar=1[v]" in fg
    assert "scale=1080:960[top]" in fg
    assert "scale=1080:960[bot]" in fg

