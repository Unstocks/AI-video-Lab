"""Deterministic acoustic measurements and non-destructive boundary signals."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

from lib.models.transcript import TimestampProvenance


def _finite_number(value: object, name: str, *, minimum: Optional[float] = None,
                   exclusive_minimum: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if exclusive_minimum is not None and result <= exclusive_minimum:
        raise ValueError(f"{name} must be > {exclusive_minimum}")
    return result


@dataclass(frozen=True)
class SilenceInterval:
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    source: Literal["ffmpeg_silencedetect", "vad"] = "ffmpeg_silencedetect"

    def __post_init__(self) -> None:
        start = _finite_number(self.start_seconds, "start_seconds", minimum=0)
        end = _finite_number(self.end_seconds, "end_seconds", minimum=start)
        duration = _finite_number(self.duration_seconds, "duration_seconds", minimum=0)
        if not math.isclose(duration, end - start, abs_tol=0.05):
            raise ValueError("duration_seconds must match end_seconds - start_seconds")
        if self.source not in ("ffmpeg_silencedetect", "vad"):
            raise ValueError("unsupported silence source")


@dataclass(frozen=True)
class SpeechInterval:
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    source: Literal["ffmpeg_silencedetect_inverse", "vad"] = "ffmpeg_silencedetect_inverse"

    def __post_init__(self) -> None:
        start = _finite_number(self.start_seconds, "start_seconds", minimum=0)
        end = _finite_number(self.end_seconds, "end_seconds", minimum=start)
        duration = _finite_number(self.duration_seconds, "duration_seconds", minimum=0)
        if not math.isclose(duration, end - start, abs_tol=0.05):
            raise ValueError("duration_seconds must match end_seconds - start_seconds")
        if self.source not in ("ffmpeg_silencedetect_inverse", "vad"):
            raise ValueError("unsupported speech source")


@dataclass(frozen=True)
class EnergyBucket:
    time_seconds: float
    loudness_lufs: float
    active: bool

    def __post_init__(self) -> None:
        _finite_number(self.time_seconds, "time_seconds", minimum=0)
        _finite_number(self.loudness_lufs, "loudness_lufs")
        if not isinstance(self.active, bool):
            raise ValueError("active must be bool")


@dataclass(frozen=True)
class ShotCut:
    timestamp_seconds: float
    method: str

    def __post_init__(self) -> None:
        _finite_number(self.timestamp_seconds, "timestamp_seconds", exclusive_minimum=0)
        if not self.method:
            raise ValueError("method must be non-empty")


@dataclass(frozen=True)
class AcousticProfile:
    audio_path: str
    video_path: Optional[str]
    total_duration_seconds: float
    silences: tuple[SilenceInterval, ...]
    speech_intervals: tuple[SpeechInterval, ...]
    energy_profile: tuple[EnergyBucket, ...]
    shot_cuts: tuple[ShotCut, ...]
    silence_threshold_db: float
    min_silence_duration_seconds: float
    timing_provenance: TimestampProvenance
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _finite_number(self.total_duration_seconds, "total_duration_seconds", minimum=0)
        _finite_number(self.silence_threshold_db, "silence_threshold_db")
        _finite_number(self.min_silence_duration_seconds, "min_silence_duration_seconds", minimum=0)
        if any(cut.timestamp_seconds >= self.total_duration_seconds for cut in self.shot_cuts):
            raise ValueError("shot cuts must be interior to the media duration")

    def is_in_silence(self, timestamp_seconds: float) -> Optional[SilenceInterval]:
        timestamp = _finite_number(timestamp_seconds, "timestamp_seconds", minimum=0)
        return next((s for s in self.silences if s.start_seconds <= timestamp <= s.end_seconds), None)

    def nearest_silence(self, timestamp_seconds: float, max_distance_seconds: float) -> Optional[SilenceInterval]:
        timestamp = _finite_number(timestamp_seconds, "timestamp_seconds", minimum=0)
        max_distance = _finite_number(max_distance_seconds, "max_distance_seconds", minimum=0)
        ranked = []
        for silence in self.silences:
            distance = 0.0 if silence.start_seconds <= timestamp <= silence.end_seconds else min(
                abs(timestamp - silence.start_seconds), abs(timestamp - silence.end_seconds))
            if distance <= max_distance:
                ranked.append((distance, -silence.duration_seconds, silence.start_seconds, silence))
        return min(ranked, default=(0, 0, 0, None))[3]

    def average_loudness_lufs(self, start_seconds: float, end_seconds: float) -> Optional[float]:
        start = _finite_number(start_seconds, "start_seconds", minimum=0)
        end = _finite_number(end_seconds, "end_seconds", minimum=0)
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        values = [b.loudness_lufs for b in self.energy_profile
                  if b.time_seconds < end and b.time_seconds + 1.0 > start and b.loudness_lufs != -120.0]
        return sum(values) / len(values) if values else None

    def shot_cuts_in_range(self, start_seconds: float, end_seconds: float) -> tuple[ShotCut, ...]:
        start = _finite_number(start_seconds, "start_seconds", minimum=0)
        end = _finite_number(end_seconds, "end_seconds", minimum=0)
        if end < start:
            raise ValueError("end_seconds must be >= start_seconds")
        return tuple(c for c in self.shot_cuts if start <= c.timestamp_seconds <= end)


@dataclass(frozen=True)
class BoundaryRefinementResult:
    original_start_seconds: float
    original_end_seconds: float
    refined_start_seconds: float
    refined_end_seconds: float
    start_provenance: TimestampProvenance
    end_provenance: TimestampProvenance
    start_adjusted: bool
    end_adjusted: bool
    start_reason: str
    end_reason: str
    nearby_shot_cuts_seconds: tuple[float, ...]
    warnings: tuple[str, ...] = ()


class VoiceActivityDetector(Protocol):
    def detect_speech_and_silence(
        self, audio_path: Path, total_duration_seconds: float
    ) -> tuple[list[SilenceInterval], list[SpeechInterval]]: ...


class AcousticProfilingError(RuntimeError):
    """Raised when required audio profiling cannot be completed."""


class AcousticProfiler:
    def __init__(
        self,
        *,
        silence_cutter: Optional[Any] = None,
        audio_energy: Optional[Any] = None,
        scene_detect: Optional[Any] = None,
        vad_detector: Optional[VoiceActivityDetector] = None,
        silence_threshold_db: float = -35.0,
        min_silence_duration_seconds: float = 0.25,
        speech_padding_seconds: float = 0.08,
        energy_threshold_lufs: float = -40.0,
    ) -> None:
        self.silence_threshold_db = _finite_number(silence_threshold_db, "silence_threshold_db")
        self.min_silence_duration_seconds = _finite_number(
            min_silence_duration_seconds, "min_silence_duration_seconds", minimum=0)
        self.speech_padding_seconds = _finite_number(speech_padding_seconds, "speech_padding_seconds", minimum=0)
        self.energy_threshold_lufs = _finite_number(energy_threshold_lufs, "energy_threshold_lufs")
        self.silence_cutter = silence_cutter
        self.audio_energy = audio_energy
        self.scene_detect = scene_detect
        self.vad_detector = vad_detector

    @staticmethod
    def _tool(name: str) -> Any:
        if name == "silence_cutter":
            from tools.video.silence_cutter import SilenceCutter
            return SilenceCutter()
        if name == "audio_energy":
            from tools.analysis.audio_energy import AudioEnergy
            return AudioEnergy()
        from tools.analysis.scene_detect import SceneDetect
        return SceneDetect()

    @staticmethod
    def _probe_duration(path: Path) -> float:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise AcousticProfilingError("ffprobe was not found on PATH")
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True, text=True, encoding="utf-8", timeout=15, check=True)
            duration = float(json.loads(result.stdout)["format"]["duration"])
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("duration must be finite and positive")
            return duration
        except Exception as exc:
            raise AcousticProfilingError(f"Could not probe media duration: {exc}") from exc

    @staticmethod
    def _invert_silences(silences: tuple[SilenceInterval, ...], duration: float) -> tuple[SpeechInterval, ...]:
        speech = []
        cursor = 0.0
        for silence in silences:
            start = min(duration, max(cursor, silence.start_seconds))
            if start > cursor:
                speech.append(SpeechInterval(cursor, start, start - cursor))
            cursor = min(duration, max(cursor, silence.end_seconds))
        if cursor < duration:
            speech.append(SpeechInterval(cursor, duration, duration - cursor))
        return tuple(speech)

    def profile(
        self,
        audio_path: str | Path,
        video_path: Optional[str | Path] = None,
        *,
        include_energy: bool = True,
        include_scene_cuts: bool = True,
    ) -> AcousticProfile:
        audio = Path(audio_path)
        video = Path(video_path) if video_path is not None else None
        if not audio.is_file():
            raise AcousticProfilingError(f"Audio file not found: {audio}")
        duration = self._probe_duration(audio)
        warnings: list[str] = []

        try:
            if self.vad_detector is not None:
                vad_silences, vad_speech = self.vad_detector.detect_speech_and_silence(audio, duration)
                silences = tuple(sorted(vad_silences, key=lambda item: item.start_seconds))
                speech = tuple(sorted(vad_speech, key=lambda item: item.start_seconds))
                if any(s.end_seconds > duration + 0.05 for s in (*silences, *speech)):
                    raise ValueError("VAD interval extends beyond media duration")
                silence_source: Literal["ffmpeg_silencedetect", "vad"] = "vad"
            else:
                cutter = self.silence_cutter or self._tool("silence_cutter")
                with tempfile.TemporaryDirectory(prefix="acoustic-profile-") as temp_dir:
                    output_json = Path(temp_dir) / "silences.json"
                    result = cutter.execute({
                        "input_path": str(audio), "mode": "mark", "output_path": str(output_json),
                        "silence_threshold_db": self.silence_threshold_db,
                        "min_silence_duration": self.min_silence_duration_seconds,
                        "padding_seconds": self.speech_padding_seconds,
                    })
                    if not getattr(result, "success", False):
                        raise AcousticProfilingError(f"SilenceCutter failed: {getattr(result, 'error', 'unknown error')}")
                    data = getattr(result, "data", {}) or {}
                    if data.get("silence_segments") == 0:
                        silences = ()
                    else:
                        if not output_json.is_file():
                            raise AcousticProfilingError(
                                "SilenceCutter reported detections but did not write its JSON output")
                        payload = json.loads(output_json.read_text(encoding="utf-8"))
                        silences = tuple(SilenceInterval(float(item["start"]), float(item["end"]),
                                                         float(item.get("duration", float(item["end"]) - float(item["start"]))))
                                         for item in payload.get("silences", []))
                if any(s.end_seconds > duration + 0.05 for s in silences):
                    raise ValueError("silence interval extends beyond media duration")
                speech = self._invert_silences(silences, duration)
                silence_source = "ffmpeg_silencedetect"
        except AcousticProfilingError:
            raise
        except Exception as exc:
            raise AcousticProfilingError(f"Silence profiling failed: {exc}") from exc

        if not silences and self.vad_detector is None and duration > 0:
            speech = (SpeechInterval(0.0, duration, duration),)

        energy: tuple[EnergyBucket, ...] = ()
        if include_energy:
            try:
                tool = self.audio_energy or self._tool("audio_energy")
                result = tool.execute({"input_path": str(audio), "energy_threshold_lufs": self.energy_threshold_lufs})
                if not getattr(result, "success", False):
                    raise RuntimeError(getattr(result, "error", "analysis failed"))
                energy = tuple(EnergyBucket(float(item["time_seconds"]), float(item["loudness_lufs"]), bool(item["active"]))
                               for item in (getattr(result, "data", {}) or {}).get("energy_profile", []))
            except Exception as exc:
                warnings.append(f"AudioEnergy unavailable: {exc}")

        shot_cuts: tuple[ShotCut, ...] = ()
        if include_scene_cuts and video is not None:
            try:
                if not video.is_file():
                    raise FileNotFoundError(f"Video file not found: {video}")
                tool = self.scene_detect or self._tool("scene_detect")
                with tempfile.TemporaryDirectory(prefix="acoustic-scenes-") as temp_dir:
                    output_json = Path(temp_dir) / "scenes.json"
                    result = tool.execute({"input_path": str(video), "output_path": str(output_json)})
                    if not getattr(result, "success", False):
                        raise RuntimeError(getattr(result, "error", "scene detection failed"))
                    scenes = (getattr(result, "data", {}) or {}).get("scenes", [])
                    method = (getattr(result, "data", {}) or {}).get("method", "ffmpeg")
                    unique = {float(scene["start_seconds"]) for scene in scenes
                              if math.isfinite(float(scene.get("start_seconds", 0)))
                              and 0 < float(scene.get("start_seconds", 0)) < duration}
                    shot_cuts = tuple(ShotCut(ts, str(method)) for ts in sorted(unique))
            except Exception as exc:
                warnings.append(f"SceneDetect unavailable: {exc}")

        return AcousticProfile(
            audio_path=str(audio), video_path=str(video) if video is not None else None,
            total_duration_seconds=duration, silences=silences, speech_intervals=speech,
            energy_profile=energy, shot_cuts=shot_cuts,
            silence_threshold_db=self.silence_threshold_db,
            min_silence_duration_seconds=self.min_silence_duration_seconds,
            timing_provenance=TimestampProvenance(
                timing_source="vad_region", alignment_method="vad_energy_or_neural", evidence_quality="medium_word",
                transformation="raw_unmodified", uncertainty_seconds=0.05, confidence=None, human_reviewed=False),
            warnings=tuple(warnings),
        )

    def suggest_boundary_refinement(
        self,
        start_seconds: float,
        end_seconds: float,
        profile: AcousticProfile,
        *,
        thought_complete_start: bool,
        thought_complete_end: bool,
        start_provenance: Optional[TimestampProvenance] = None,
        end_provenance: Optional[TimestampProvenance] = None,
        max_snap_window_seconds: float = 1.5,
        speech_padding_seconds: float = 0.08,
        min_pause_duration_seconds: float = 0.25,
    ) -> BoundaryRefinementResult:
        start = _finite_number(start_seconds, "start_seconds", minimum=0)
        end = _finite_number(end_seconds, "end_seconds", minimum=0)
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        max_window = _finite_number(max_snap_window_seconds, "max_snap_window_seconds", minimum=0)
        padding = _finite_number(speech_padding_seconds, "speech_padding_seconds", minimum=0)
        min_pause = _finite_number(min_pause_duration_seconds, "min_pause_duration_seconds", minimum=0)
        if not isinstance(thought_complete_start, bool) or not isinstance(thought_complete_end, bool):
            raise ValueError("thought_complete flags must be bool")
        start_prov = start_provenance or TimestampProvenance()
        end_prov = end_provenance or TimestampProvenance()
        refined_start, refined_end = start, end
        start_adjusted = end_adjusted = False
        start_reason = "held: start boundary not marked thought-complete" if not thought_complete_start else "held: no qualifying nearby silence"
        end_reason = "held: end boundary not marked thought-complete" if not thought_complete_end else "held: no qualifying nearby silence"

        def choose(boundary: float) -> Optional[SilenceInterval]:
            ranked = []
            for silence in profile.silences:
                if silence.duration_seconds < min_pause:
                    continue
                distance = 0.0 if silence.start_seconds <= boundary <= silence.end_seconds else min(
                    abs(boundary - silence.start_seconds), abs(boundary - silence.end_seconds))
                if distance <= max_window:
                    ranked.append((distance, -silence.duration_seconds, silence.start_seconds, silence))
            return min(ranked, default=(0, 0, 0, None))[3]

        if thought_complete_start:
            silence = choose(start)
            if silence is not None:
                candidate = min(profile.total_duration_seconds, max(0.0, max(silence.start_seconds, silence.end_seconds - padding)))
                if abs(candidate - start) > 1e-6:
                    refined_start = candidate
                    start_adjusted = True
                    start_reason = "aligned before nearby speech onset with padding"
        if thought_complete_end:
            silence = choose(end)
            if silence is not None:
                candidate = min(profile.total_duration_seconds, max(0.0, min(silence.end_seconds, silence.start_seconds + padding)))
                if abs(candidate - end) > 1e-6:
                    refined_end = candidate
                    end_adjusted = True
                    end_reason = "aligned after nearby speech offset with padding"

        warnings = []
        if refined_end <= refined_start:
            refined_start, refined_end = start, end
            start_adjusted = end_adjusted = False
            start_prov = start_provenance or TimestampProvenance()
            end_prov = end_provenance or TimestampProvenance()
            start_reason = "held: snap aborted to preserve a valid interval"
            end_reason = "held: snap aborted to preserve a valid interval"
            warnings.append("boundary snap aborted: would invert or collapse interval")
        else:
            if start_adjusted:
                start_prov = TimestampProvenance(
                    timing_source="vad_region", alignment_method="vad_energy_or_neural", evidence_quality="medium_word",
                    transformation="silence_proximity_adjusted", uncertainty_seconds=0.05,
                    confidence=None, human_reviewed=False, original_seconds=start)
            if end_adjusted:
                end_prov = TimestampProvenance(
                    timing_source="vad_region", alignment_method="vad_energy_or_neural", evidence_quality="medium_word",
                    transformation="silence_proximity_adjusted", uncertainty_seconds=0.05,
                    confidence=None, human_reviewed=False, original_seconds=end)
        nearby = tuple(c.timestamp_seconds for c in profile.shot_cuts
                       if start - max_window <= c.timestamp_seconds <= end + max_window)
        return BoundaryRefinementResult(start, end, refined_start, refined_end, start_prov, end_prov,
                                        start_adjusted, end_adjusted, start_reason, end_reason, nearby, tuple(warnings))
