"""Unit tests for lib.camera_tracker (SmoothedCameraman & SpeakerTracker)."""

from __future__ import annotations

from lib.camera_tracker import SmoothedCameraman, SpeakerTracker


class TestSmoothedCameraman:
    def test_stationary_inside_safe_zone(self):
        cam = SmoothedCameraman(1080, 1920, 1920, 1080)
        x0, _, _, _ = cam.get_crop_box()
        # Small shift well within safe_zone_radius (0.25 * 606 ~= 151px)
        cam.update_target([960 - 40, 200, 100, 100])
        x1, _, _, _ = cam.get_crop_box()
        assert x1 == x0

    def test_three_frame_jump_confirmation_rejects_lone_outlier(self):
        cam = SmoothedCameraman(1080, 1920, 1920, 1080, jump_confirm_frames=3)
        initial_target = cam.target_center_x

        # Single outlier detection far right -> ignored
        cam.update_target([1600, 200, 100, 100])
        assert cam.target_center_x == initial_target

        # Contradictory outlier far left -> resets pending counter, still ignored
        cam.update_target([100, 200, 100, 100])
        assert cam.target_center_x == initial_target

        # 3 consistent detections far right -> confirmed!
        cam.update_target([1600, 200, 100, 100])
        cam.update_target([1610, 200, 100, 100])
        assert cam.target_center_x == initial_target  # 2 of 3
        cam.update_target([1605, 200, 100, 100])
        assert cam.target_center_x == 1655.0  # 3 of 3 accepted!

    def test_begin_scene_snaps_immediately_without_panning(self):
        cam = SmoothedCameraman(1080, 1920, 1920, 1080, jump_confirm_frames=3)
        cam.begin_scene()
        cam.update_target([1500, 200, 100, 100])  # center = 1550
        assert cam.target_center_x == 1550.0
        assert cam.current_center_x == 1550.0
        x1, _, x2, _ = cam.get_crop_box()
        assert x2 - x1 == cam.crop_width
        assert x1 > 1000

    def test_linear_pan_speeds_normal_vs_fast(self):
        cam = SmoothedCameraman(1080, 1920, 1920, 1080, jump_confirm_frames=1)
        # Offset > 0.5 * crop_width -> fast pan (15 px/f)
        cam.update_target([1500, 200, 100, 100])
        c0 = cam.current_center_x
        cam.get_crop_box()
        assert cam.current_center_x - c0 == 15.0

        # Offset inside (0.25*cw, 0.5*cw) -> slow pan (3 px/f)
        cam2 = SmoothedCameraman(1080, 1920, 1920, 1080, jump_confirm_frames=1)
        cam2.target_center_x = cam2.current_center_x + cam2.crop_width * 0.35
        c1 = cam2.current_center_x
        cam2.get_crop_box()
        assert cam2.current_center_x - c1 == 3.0


class TestSpeakerTracker:
    def test_sticky_hysteresis_and_cooldown_hold_on_blink(self):
        tr = SpeakerTracker(cooldown_frames=30)
        left = {"box": [300, 200, 140, 140], "score": 140 * 140}
        right = {"box": [1400, 200, 150, 150], "score": 150 * 150}

        # Frame 0: lock onto left
        box0 = tr.get_target([left], frame_number=0, width=1920)
        assert box0 == left["box"]
        active_id = tr.active_speaker_id

        # Frame 5: left blinks out, right appears -> cooldown holds (returns None)
        box5 = tr.get_target([right], frame_number=5, width=1920)
        assert box5 is None
        assert tr.active_speaker_id == active_id

        # Frame 40: cooldown expired, only right present -> switches cleanly to right
        box40 = tr.get_target([right], frame_number=40, width=1920)
        assert box40 == right["box"]
        assert tr.active_speaker_id != active_id

    def test_reset_clears_cooldown_at_scene_cut(self):
        tr = SpeakerTracker(cooldown_frames=30)
        left = {"box": [300, 200, 140, 140], "score": 140 * 140}
        right = {"box": [1400, 200, 140, 140], "score": 140 * 140}

        tr.get_target([left], frame_number=0, width=1920)
        tr.reset()
        box = tr.get_target([right], frame_number=2, width=1920)
        assert box == right["box"]
