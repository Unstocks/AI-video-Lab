"""Unit tests for lib.punch_in (smoothstep zoom, crop boxes, sendcmd, beat merge)."""

from __future__ import annotations

from lib.punch_in import (
    FALL_SECONDS,
    HOLD_SECONDS,
    RISE_SECONDS,
    crop_boxes,
    merge_emphasis_times,
    sendcmd_lines,
    zoom_curve,
)


def test_zoom_curve_smoothstep_and_non_compounding_overlap():
    fps = 30.0
    # Two beats overlapping by 0.5s should take max(), NEVER multiply/compound
    curve = zoom_curve(n_frames=180, fps=fps, emphasis_times=[1.0, 1.5], max_zoom=1.12)
    assert curve[0] == 1.0
    assert abs(max(curve) - 1.12) < 1e-6
    # During hold (t=1.4s -> frame 42), curve sits at peak 1.12
    assert abs(curve[42] - 1.12) < 1e-6
    # After span ends (1.5 + RISE + HOLD + FALL = 3.6s -> frame 115), back to 1.0
    end_f = int((1.5 + RISE_SECONDS + HOLD_SECONDS + FALL_SECONDS + 0.2) * fps)
    assert curve[end_f] == 1.0


def test_crop_boxes_even_dimensions_and_clamped():
    xs = [0, 650, 1300]
    zooms = [1.0, 1.12, 1.12]
    boxes = crop_boxes(xs, zooms, crop_w=606, crop_h=1080, orig_w=1920, orig_h=1080)
    assert len(boxes) == 3
    for w, h, x, y in boxes:
        assert w % 2 == 0 and h % 2 == 0
        assert x % 2 == 0 and y % 2 == 0
        assert 0 <= x <= 1920 - w
        assert 0 <= y <= 1080 - h
    # Zoomed box is strictly smaller than unzoomed box
    assert boxes[1][0] < boxes[0][0] and boxes[1][1] < boxes[0][1]


def test_sendcmd_lines_dedupes_unchanged_parameters():
    boxes = [
        (606, 1080, 100, 0),
        (606, 1080, 100, 0),  # identical -> skipped
        (606, 1080, 110, 0),  # only x changed -> 1 line
        (540, 964, 142, 58),  # all 4 changed -> 4 lines
    ]
    lines = sendcmd_lines(boxes, fps=30.0, target="crop@c")
    assert len(lines) == 4 + 1 + 4
    assert any("crop@c x 110;" in ln for ln in lines)
    assert any("crop@c w 540;" in ln for ln in lines)


def test_merge_emphasis_times_prioritizes_editorial_beats_and_enforces_gap():
    merged = merge_emphasis_times(
        audio_beats=[2.0, 10.0, 25.0, 46.0],
        editorial_beats=[3.0, 40.0],
        min_gap=18.0,
    )
    # 3.0 & 40.0 (editorial) win; audio 2.0/10.0 are within 18s of 3.0; 46.0 is within 18s of 40.0;
    # audio 25.0 is >= 18s from 3.0 (22s) and 15s from 40.0 (too close -> dropped!)
    assert merged == [3.0, 40.0]

    merged2 = merge_emphasis_times(
        audio_beats=[2.0, 22.0, 50.0],
        editorial_beats=[3.0],
        min_gap=18.0,
    )
    assert merged2 == [3.0, 22.0, 50.0]

