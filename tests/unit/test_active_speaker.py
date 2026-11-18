"""Unit tests for lib.active_speaker (mouth-motion + audio RMS gate & hysteresis)."""

from __future__ import annotations

from lib.active_speaker import (
    attribute_windows,
    hold,
    is_conversation,
    mouth_region,
    normalise_activity,
    shares,
    speaker_xs,
)


def test_mouth_region_targets_lower_face_and_clamps():
    x0, y0, x1, y1 = mouth_region([100, 50, 200, 200], frame_w=480, frame_h=270, scale=2.0)
    assert 0 <= x0 < x1 <= 480
    assert 0 <= y0 < y1 <= 270
    # Scaled face y=[25..125]; mouth centered at 25 + 0.72*100 = 97
    assert y0 < 97 < y1


def test_normalise_activity_removes_lighting_bias():
    # Speaker 0 is 10x brighter/higher contrast than speaker 1 even when quiet,
    # yet both alternate speaking cleanly.
    raw = [
        [20.0, 1.0],
        [50.0, 1.0],
        [52.0, 1.1],
        [20.0, 4.0],
        [21.0, 4.2],
        [20.0, 4.1],
        [48.0, 1.0],
        [20.0, 4.0],
    ]
    norm = normalise_activity(raw)
    verdicts = attribute_windows(norm, loudness=[0.8] * len(raw))
    assert is_conversation(verdicts)
    s0, s1 = shares(verdicts)
    assert s0 >= 0.3 and s1 >= 0.3


def test_audio_floor_rejects_silent_nods_and_is_conversation_gates_silent_listener():
    activity = [
        [5.0, 0.2],  # speaker 0 talking
        [4.5, 0.2],
        [0.1, 8.0],  # speaker 1 nodding silently (loudness below AUDIO_FLOOR)
        [0.1, 7.5],  # silent laugh
        [5.2, 0.1],
    ]
    loudness = [0.7, 0.8, 0.05, 0.04, 0.9]
    verdicts = attribute_windows(activity, loudness)
    assert verdicts == [0, 0, None, None, 0]
    assert shares(verdicts) == (1.0, 0.0)
    assert is_conversation(verdicts) is False


def test_hold_prevents_flapping_and_backfills_leadin():
    # Lead-in unclear, then speaker 0 talks, speaker 1 interrupts for 1 window (ignored),
    # then speaker 1 holds 3 consecutive windows (takes over).
    verdicts = [None, None, 0, 0, 1, 0, 1, 1, 1, None]
    held = hold(verdicts, min_windows=3)
    assert held == [0, 0, 0, 0, 0, 0, 0, 0, 1, 1]


def test_speaker_xs_produces_clamped_hard_cut_positions():
    held = [0, 0, 1, 1]
    centres = [(400.0, 300.0, 120.0, 120.0), (1500.0, 300.0, 120.0, 120.0)]
    xs = speaker_xs(held, centres, crop_w=606, orig_w=1920, n_frames=40, fps=25.0, window_s=0.4)
    assert len(xs) == 40
    # First 20 frames (0.0..0.8s) -> speaker 0; next 20 frames -> speaker 1
    assert all(x == 97 for x in xs[:20])
    assert all(x == 1197 for x in xs[20:])
