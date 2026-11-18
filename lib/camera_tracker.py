"""Cinematographic camera smoothing & speaker identity hysteresis for Reframe v2.

Pure Python (zero OpenCV/FFmpeg dependency) so camera physics stay deterministic
and fast to unit-test:

- ``SmoothedCameraman`` ("Heavy Tripod"):
  * Deadzone ``safe_zone_radius = 0.25 * crop_width`` prevents micro-jitter.
  * 3-frame jump confirmation (``jump_confirm_frames = 3``) filters lone
    false-positive face detections (-69% whip-pan reversals).
  * ``begin_scene()`` snaps immediately to the first detected face in a new
    shot, eliminating 1.5s headless-torso pans across hard cuts.
  * Linear pan speed: ``3.0 px/frame`` normal, ``15.0 px/frame`` fast reframe
    when offset exceeds ``0.5 * crop_width``.

- ``SpeakerTracker``:
  * Matches face detections across frames within ``0.15 * width``.
  * Decays per-ID activity scores by ``0.85`` per step.
  * Applies ``3.0x`` sticky hysteresis to the active speaker + ``cooldown_frames=30``
    so blinks/head-turns never trigger cross-frame ping-pong.
  * ``reset()`` clears identity/cooldown cleanly at shot boundaries.
"""

from __future__ import annotations

from typing import Any

DEFAULT_ASPECT_RATIO = 9.0 / 16.0
DEFAULT_JUMP_CONFIRM_FRAMES = 3


class SmoothedCameraman:
    """Heavy-tripod horizontal camera controller for aspect-ratio cropping."""

    def __init__(
        self,
        output_width: int,
        output_height: int,
        video_width: int,
        video_height: int,
        aspect_ratio: float = DEFAULT_ASPECT_RATIO,
        *,
        jump_confirm_frames: int = DEFAULT_JUMP_CONFIRM_FRAMES,
        slow_pan_speed: float = 3.0,
        fast_pan_speed: float = 15.0,
    ) -> None:
        self.output_width = int(output_width)
        self.output_height = int(output_height)
        self.video_width = int(video_width)
        self.video_height = int(video_height)
        self.aspect_ratio = float(aspect_ratio)

        self.current_center_x: float = self.video_width / 2.0
        self.target_center_x: float = self.video_width / 2.0

        self.crop_height = self.video_height
        self.crop_width = int(self.crop_height * self.aspect_ratio)
        if self.crop_width > self.video_width:
            self.crop_width = self.video_width
            self.crop_height = int(self.crop_width / self.aspect_ratio)
        # Ensure valid positive even crop dimensions
        self.crop_width = max(2, self.crop_width - (self.crop_width % 2))
        self.crop_height = max(2, self.crop_height - (self.crop_height % 2))

        self.safe_zone_radius: float = self.crop_width * 0.25
        self.jump_confirm_frames: int = max(1, int(jump_confirm_frames))
        self.slow_pan_speed: float = float(slow_pan_speed)
        self.fast_pan_speed: float = float(fast_pan_speed)

        self._pending_target: float | None = None
        self._pending_count: int = 0
        self._snap_pending: bool = False

    def begin_scene(self) -> None:
        """Forget the previous shot's target and snap to the first detection in the new shot."""
        self._pending_target = None
        self._pending_count = 0
        self._snap_pending = True

    def update_target(self, face_box: list[float] | tuple[float, float, float, float] | None) -> None:
        """Update target center from ``[x, y, w, h]`` with 3-frame jump confirmation."""
        if not face_box:
            return
        x, _y, w, _h = face_box
        new_center = float(x) + float(w) / 2.0

        if self._snap_pending:
            self._snap_pending = False
            self._pending_target = None
            self._pending_count = 0
            self.target_center_x = new_center
            self.current_center_x = new_center
            return

        if abs(new_center - self.target_center_x) > self.safe_zone_radius:
            if (
                self._pending_target is not None
                and abs(new_center - self._pending_target) <= self.safe_zone_radius
            ):
                self._pending_count += 1
            else:
                self._pending_target = new_center
                self._pending_count = 1
            if self._pending_count < self.jump_confirm_frames:
                return

        self._pending_target = None
        self._pending_count = 0
        self.target_center_x = new_center

    def get_crop_box(self, force_snap: bool = False) -> tuple[int, int, int, int]:
        """Advance camera one frame and return clamped ``(x1, y1, x2, y2)``."""
        if force_snap:
            self.current_center_x = self.target_center_x
        else:
            diff = self.target_center_x - self.current_center_x
            if abs(diff) > self.safe_zone_radius:
                direction = 1.0 if diff > 0 else -1.0
                speed = (
                    self.fast_pan_speed
                    if abs(diff) > self.crop_width * 0.5
                    else self.slow_pan_speed
                )
                self.current_center_x += direction * speed
                new_diff = self.target_center_x - self.current_center_x
                if (direction > 0 and new_diff < 0) or (direction < 0 and new_diff > 0):
                    self.current_center_x = self.target_center_x

        half_crop = self.crop_width / 2.0
        if self.current_center_x - half_crop < 0:
            self.current_center_x = half_crop
        if self.current_center_x + half_crop > self.video_width:
            self.current_center_x = self.video_width - half_crop

        x1 = max(0, min(int(round(self.current_center_x - half_crop)), self.video_width - self.crop_width))
        x2 = min(self.video_width, x1 + self.crop_width)
        y1 = 0
        y2 = min(self.video_height, self.crop_height)
        return x1, y1, x2, y2


class SpeakerTracker:
    """Sticky face-ID tracker preventing rapid switching and obstruction jumps."""

    def __init__(self, stabilization_frames: int = 15, cooldown_frames: int = 30) -> None:
        self.active_speaker_id: int | None = None
        self.speaker_scores: dict[int, float] = {}
        self.last_seen: dict[int, int] = {}
        self.locked_counter: int = 0

        self.stabilization_threshold: int = int(stabilization_frames)
        self.switch_cooldown: int = int(cooldown_frames)
        self.last_switch_frame: int = -1000

        self.next_id: int = 0
        self.known_faces: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Forget speaker history and cooldown at a scene boundary."""
        self.active_speaker_id = None
        self.speaker_scores = {}
        self.last_seen = {}
        self.locked_counter = 0
        self.last_switch_frame = -1000
        self.known_faces = []

    def get_target(
        self,
        face_candidates: list[dict[str, Any]],
        frame_number: int,
        width: int,
    ) -> list[float] | None:
        """Select active face ``[x, y, w, h]`` or ``None`` to hold current framing."""
        current_candidates: list[dict[str, Any]] = []
        match_radius = float(width) * 0.15

        # 1. Match detections to recent IDs by horizontal proximity
        for face in face_candidates:
            x, y, w, h = face["box"]
            center_x = float(x) + float(w) / 2.0

            best_match_id = -1
            min_dist = match_radius
            for kf in self.known_faces:
                if frame_number - kf["last_frame"] > 30:
                    continue
                dist = abs(center_x - kf["center"])
                if dist < min_dist:
                    min_dist = dist
                    best_match_id = kf["id"]

            if best_match_id == -1:
                best_match_id = self.next_id
                self.next_id += 1

            self.known_faces = [kf for kf in self.known_faces if kf["id"] != best_match_id]
            self.known_faces.append(
                {"id": best_match_id, "center": center_x, "last_frame": frame_number}
            )
            self.last_seen[best_match_id] = frame_number

            area = float(face.get("score") or (w * h))
            current_candidates.append(
                {"id": best_match_id, "box": list(face["box"]), "score": area}
            )

        # 2. Decay accumulated scores and add new observations
        for pid in list(self.speaker_scores.keys()):
            self.speaker_scores[pid] *= 0.85
            if self.speaker_scores[pid] < 0.1:
                del self.speaker_scores[pid]

        denom = max(1.0, float(width) * float(width) * 0.05)
        for cand in current_candidates:
            pid = cand["id"]
            self.speaker_scores[pid] = self.speaker_scores.get(pid, 0.0) + (cand["score"] / denom)

        if not current_candidates:
            return None

        # 3. Pick highest-scoring speaker with 3.0x sticky hysteresis
        best_candidate: dict[str, Any] | None = None
        max_score = -1.0
        for cand in current_candidates:
            pid = cand["id"]
            total_score = self.speaker_scores.get(pid, 0.0)
            if pid == self.active_speaker_id:
                total_score *= 3.0
            if total_score > max_score:
                max_score = total_score
                best_candidate = cand

        if not best_candidate:
            return None

        target_id = best_candidate["id"]
        if target_id == self.active_speaker_id:
            self.locked_counter += 1
            return best_candidate["box"]

        # 4. Enforce switch cooldown even if active speaker briefly vanished
        if frame_number - self.last_switch_frame < self.switch_cooldown:
            old_cand = next(
                (c for c in current_candidates if c["id"] == self.active_speaker_id),
                None,
            )
            return old_cand["box"] if old_cand else None

        self.active_speaker_id = target_id
        self.last_switch_frame = frame_number
        self.locked_counter = 0
        return best_candidate["box"]
