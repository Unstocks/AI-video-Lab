"""Unit tests for lib.face_detector and upgraded tools.analysis.face_tracker."""

from __future__ import annotations

import numpy as np

from lib.face_detector import MultiFaceDetector, default_yunet_model_path, read_frames_at
from tools.analysis.face_tracker import FaceTracker
from tools.base_tool import ToolStatus


class _FakeCapture:
    def __init__(self, n_frames: int):
        self.n_frames = n_frames
        self.pos = 0
        self.seeks: list[int] = []
        self.grabs = 0

    def set(self, _prop: int, val: float) -> bool:
        self.pos = int(val)
        self.seeks.append(self.pos)
        return True

    def grab(self) -> bool:
        if self.pos >= self.n_frames:
            return False
        self.pos += 1
        self.grabs += 1
        return True

    def read(self):
        if self.pos >= self.n_frames:
            return False, None
        frame = np.full((8, 8, 3), self.pos, dtype=np.int32)
        self.pos += 1
        return True, frame


def test_read_frames_at_uses_forward_grab_and_caches_repeats():
    cap = _FakeCapture(100)
    frames = list(read_frames_at(cap, [0, 5, 5, 12], max_forward=50))
    assert len(frames) == 4
    assert int(frames[0][0, 0, 0]) == 0
    assert int(frames[1][0, 0, 0]) == 5
    assert frames[2] is frames[1]  # repeated index returns cached frame
    assert int(frames[3][0, 0, 0]) == 12
    assert cap.seeks == []  # zero seeks for forward small steps
    assert cap.grabs == (5 - 1) + (12 - 6)


def test_read_frames_at_seeks_on_large_jump_or_backward():
    cap = _FakeCapture(500)
    frames = list(read_frames_at(cap, [10, 450, 20, 600], max_forward=100))
    assert int(frames[0][0, 0, 0]) == 10
    assert int(frames[1][0, 0, 0]) == 450
    assert int(frames[2][0, 0, 0]) == 20
    assert frames[3] is None
    assert cap.seeks == [450, 20, 600]


def test_yunet_model_is_bundled_and_face_tracker_is_available():
    model = default_yunet_model_path()
    assert model.is_file() and model.stat().st_size > 100_000
    with MultiFaceDetector() as det:
        assert det.backend == "yunet"
        assert det.is_available() and det.is_high_accuracy()
        # Blank frame yields empty list cleanly (no crash)
        blank = np.zeros((360, 640, 3), dtype=np.uint8)
        assert det.detect(blank) == []
    assert FaceTracker().get_status() == ToolStatus.AVAILABLE


def test_detector_falls_back_gracefully_when_yunet_missing(tmp_path):
    with MultiFaceDetector(yunet_model_path=tmp_path / "missing.onnx") as det:
        assert det.backend in {"mediapipe", "haar", "none"}
        blank = np.zeros((180, 320, 3), dtype=np.uint8)
        assert det.detect(blank) == []
