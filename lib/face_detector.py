"""Multi-backend face detector & forward-pass frame sampler for Smart Reframe v2.

Detector priority order (all CPU-fast on <=640px frames, Python 3.14 native):
1. OpenCV YuNet ONNX (``cv2.FaceDetectorYN``) — handles side-profile podcast
   faces natively on Python 3.14 without MediaPipe wheel constraints.
2. MediaPipe FaceDetection (when installed).
3. OpenCV Haar Cascade (frontal + profile fallback).
4. Graceful empty fallback (never crashes callers when OpenCV is absent).

Also provides ``read_frames_at(cap, indices, max_forward=300)`` which replaces
per-sample H.264 random seeks with a single forward ``cap.grab()`` pass (~15x
CPU speedup on GOP-encoded clips).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Iterable, Iterator

logger = logging.getLogger(__name__)

DETECT_MAX_WIDTH = 640
MAX_FORWARD = 300
DEFAULT_YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"

_YUNET_CACHE_LOCK = threading.Lock()
_YUNET_CACHE: dict[tuple[str, float], tuple[Any, threading.Lock]] = {}


def default_yunet_model_path() -> Path:
    """Return canonical repo location for the MIT-licensed OpenCV Zoo YuNet ONNX model."""
    return Path(__file__).resolve().parent.parent / "assets" / "models" / DEFAULT_YUNET_FILENAME


def _downscale_for_detection(frame: Any, max_width: int = DETECT_MAX_WIDTH) -> tuple[Any, float]:
    """Return ``(small_frame, scale)`` where ``scale`` maps small coords to original."""
    import cv2

    h, w = frame.shape[:2]
    if w <= max_width:
        return frame, 1.0
    scale = w / float(max_width)
    small_h = max(2, int(round(h / scale)))
    small = cv2.resize(frame, (max_width, small_h), interpolation=cv2.INTER_AREA)
    return small, scale


def read_frames_at(cap: Any, indices: Iterable[int], max_forward: int = MAX_FORWARD) -> Iterator[Any]:
    """Yield ``cap.read()`` frames for each index in ``indices`` using forward ``grab()``.

    ``cap`` should be freshly opened at frame 0. For non-decreasing indices
    within ``max_forward`` of the current cursor, advances via ``cap.grab()``
    instead of expensive keyframe seeks. Repeated indices yield the cached
    frame object (treat yielded frames as read-only).
    """
    import cv2

    pos = 0
    last: tuple[int | None, Any] = (None, None)
    for raw_idx in indices:
        idx = int(raw_idx)
        if idx == last[0]:
            yield last[1]
            continue
        if idx < 0:
            last = (idx, None)
            yield None
            continue
        if idx < pos or (idx - pos) > max_forward:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            pos = idx
        frame = None
        while pos < idx:
            if not cap.grab():
                break
            pos += 1
        if pos == idx:
            ok, frame = cap.read()
            pos += 1
            if not ok:
                frame = None
        last = (idx, frame)
        yield frame


class MultiFaceDetector:
    """Thread-safe multi-face detector with YuNet -> MediaPipe -> Haar fallback."""

    def __init__(
        self,
        *,
        min_confidence: float = 0.5,
        yunet_model_path: str | Path | None = None,
        max_width: int = DETECT_MAX_WIDTH,
    ) -> None:
        self.min_confidence = float(min_confidence)
        self.max_width = max(64, int(max_width))
        self.yunet_model_path = (
            Path(yunet_model_path) if yunet_model_path is not None else default_yunet_model_path()
        )
        self._lock = threading.Lock()
        self._backend: str = "none"
        self._yunet: Any = None
        self._mediapipe: Any = None
        self._haar_frontal: Any = None
        self._haar_profile: Any = None
        self._init_backend()

    @property
    def backend(self) -> str:
        """Active backend name: ``yunet``, ``mediapipe``, ``haar``, or ``none``."""
        return self._backend

    def is_available(self) -> bool:
        return self._backend != "none"

    def is_high_accuracy(self) -> bool:
        return self._backend in ("yunet", "mediapipe")

    def _init_backend(self) -> None:
        try:
            import cv2
        except ImportError:
            self._backend = "none"
            return

        # 1. OpenCV YuNet ONNX (fast, accurate on profile faces, Python 3.14 native)
        if (
            hasattr(cv2, "FaceDetectorYN")
            and self.yunet_model_path.is_file()
            and self.yunet_model_path.stat().st_size > 1024
        ):
            try:
                cache_key = (str(self.yunet_model_path.resolve()), round(self.min_confidence, 4))
                with _YUNET_CACHE_LOCK:
                    cached = _YUNET_CACHE.get(cache_key)
                    if cached is None:
                        detector = cv2.FaceDetectorYN.create(
                            str(self.yunet_model_path),
                            "",
                            (320, 320),
                            score_threshold=self.min_confidence,
                            nms_threshold=0.3,
                            top_k=5000,
                        )
                        cached = (detector, threading.Lock())
                        _YUNET_CACHE[cache_key] = cached
                self._yunet, self._lock = cached
                self._backend = "yunet"
                return
            except Exception as exc:
                logger.warning("YuNet init failed (%s); falling back", exc)

        # 2. MediaPipe FaceDetection
        try:
            import mediapipe as mp

            if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_detection"):
                self._mediapipe = mp.solutions.face_detection.FaceDetection(
                    model_selection=1,
                    min_detection_confidence=self.min_confidence,
                )
                self._backend = "mediapipe"
                return
        except Exception:
            pass

        # 3. OpenCV Haar Cascade (frontal + profile)
        try:
            haar_dir = getattr(getattr(cv2, "data", None), "haarcascades", "")
            frontal_xml = Path(haar_dir) / "haarcascade_frontalface_default.xml"
            if frontal_xml.is_file():
                clf = cv2.CascadeClassifier(str(frontal_xml))
                if not clf.empty():
                    self._haar_frontal = clf
                    profile_xml = Path(haar_dir) / "haarcascade_profileface.xml"
                    if profile_xml.is_file():
                        prof = cv2.CascadeClassifier(str(profile_xml))
                        if not prof.empty():
                            self._haar_profile = prof
                    self._backend = "haar"
                    return
        except Exception as exc:
            logger.warning("Haar cascade init failed (%s)", exc)

        self._backend = "none"

    def detect(self, frame: Any) -> list[dict[str, Any]]:
        """Detect faces in a BGR frame.

        Returns a list of dicts:
        ``{"box": [x, y, w, h], "score": float(w * h), "confidence": float}``
        in **original** frame pixel coordinates.
        """
        if frame is None or self._backend == "none":
            return []
        if not hasattr(frame, "shape") or len(frame.shape) < 2:
            return []
        orig_h, orig_w = int(frame.shape[0]), int(frame.shape[1])
        if orig_w <= 0 or orig_h <= 0:
            return []

        small, scale = _downscale_for_detection(frame, max_width=self.max_width)
        sh, sw = int(small.shape[0]), int(small.shape[1])

        with self._lock:
            if self._backend == "yunet":
                return self._detect_yunet(small, sw, sh, scale, orig_w, orig_h)
            if self._backend == "mediapipe":
                return self._detect_mediapipe(small, orig_w, orig_h)
            if self._backend == "haar":
                return self._detect_haar(small, scale, orig_w, orig_h)
        return []

    def _detect_yunet(
        self, small: Any, sw: int, sh: int, scale: float, orig_w: int, orig_h: int
    ) -> list[dict[str, Any]]:
        self._yunet.setInputSize((sw, sh))
        _ok, faces = self._yunet.detect(small)
        if faces is None or len(faces) == 0:
            return []
        out: list[dict[str, Any]] = []
        for row in faces:
            fx, fy, fw, fh = float(row[0]), float(row[1]), float(row[2]), float(row[3])
            conf = float(row[-1]) if len(row) >= 5 else self.min_confidence
            if conf < self.min_confidence or fw <= 1 or fh <= 1:
                continue
            x = max(0, min(int(round(fx * scale)), orig_w - 1))
            y = max(0, min(int(round(fy * scale)), orig_h - 1))
            w = max(1, min(int(round(fw * scale)), orig_w - x))
            h = max(1, min(int(round(fh * scale)), orig_h - y))
            out.append({"box": [x, y, w, h], "score": float(w * h), "confidence": round(conf, 4)})
        out.sort(key=lambda c: c["score"], reverse=True)
        return out

    def _detect_mediapipe(self, small: Any, orig_w: int, orig_h: int) -> list[dict[str, Any]]:
        import cv2

        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        results = self._mediapipe.process(rgb)
        if not results or not results.detections:
            return []
        out: list[dict[str, Any]] = []
        for det in results.detections:
            bbox = det.location_data.relative_bounding_box
            conf = float(det.score[0]) if det.score else self.min_confidence
            x = max(0, min(int(round(bbox.xmin * orig_w)), orig_w - 1))
            y = max(0, min(int(round(bbox.ymin * orig_h)), orig_h - 1))
            w = max(1, min(int(round(bbox.width * orig_w)), orig_w - x))
            h = max(1, min(int(round(bbox.height * orig_h)), orig_h - y))
            out.append({"box": [x, y, w, h], "score": float(w * h), "confidence": round(conf, 4)})
        out.sort(key=lambda c: c["score"], reverse=True)
        return out

    def _detect_haar(
        self, small: Any, scale: float, orig_w: int, orig_h: int
    ) -> list[dict[str, Any]]:
        import cv2

        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        raw_boxes = list(
            self._haar_frontal.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
            )
        )
        if not raw_boxes and self._haar_profile is not None:
            raw_boxes = list(
                self._haar_profile.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24)
                )
            )
        out: list[dict[str, Any]] = []
        for fx, fy, fw, fh in raw_boxes:
            x = max(0, min(int(round(fx * scale)), orig_w - 1))
            y = max(0, min(int(round(fy * scale)), orig_h - 1))
            w = max(1, min(int(round(fw * scale)), orig_w - x))
            h = max(1, min(int(round(fh * scale)), orig_h - y))
            out.append({"box": [x, y, w, h], "score": float(w * h), "confidence": 0.7})
        out.sort(key=lambda c: c["score"], reverse=True)
        return out

    def close(self) -> None:
        if self._mediapipe is not None:
            try:
                self._mediapipe.close()
            except Exception:
                pass
            self._mediapipe = None

    def __enter__(self) -> "MultiFaceDetector":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
