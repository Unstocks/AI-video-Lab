"""Deterministic acoustic profiling tests, including real FFmpeg fixtures."""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from lib.acoustic_profiler import (
    AcousticProfile,
    AcousticProfiler,
    AcousticProfilingError,
    EnergyBucket,
    SilenceInterval,
    SpeechInterval,
)
from lib.models.transcript import TimestampProvenance


FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(not FFMPEG or not FFPROBE, reason="FFmpeg/ffprobe are required")


def _run_ffmpeg(*args: str) -> None:
    result = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args],
                            capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr


def _silence_tone_wav(path: Path) -> Path:
    args = []
    for source in (
        "sine=frequency=440:sample_rate=48000:duration=1.5",
        "anullsrc=r=48000:cl=mono:d=1.0",
        "sine=frequency=440:sample_rate=48000:duration=2.0",
        "anullsrc=r=48000:cl=mono:d=1.0",
        "sine=frequency=440:sample_rate=48000:duration=1.5",
    ):
        args.extend(["-f", "lavfi", "-i", source])
    _run_ffmpeg(*args, "-filter_complex", "[0:a][1:a][2:a][3:a][4:a]concat=n=5:v=0:a=1[out]",
                "-map", "[out]", "-c:a", "pcm_s16le", str(path))
    return path


def _continuous_tone_wav(path: Path, duration: float = 3.0) -> Path:
    _run_ffmpeg("-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
                "-c:a", "pcm_s16le", str(path))
    return path


def _profile_with_pauses() -> AcousticProfile:
    silences = (SilenceInterval(1.5, 2.5, 1.0), SilenceInterval(4.5, 5.5, 1.0))
    return AcousticProfile("audio.wav", None, 7.0, silences,
                           (SpeechInterval(0, 1.5, 1.5), SpeechInterval(2.5, 4.5, 2), SpeechInterval(5.5, 7, 1.5)),
                           (), (), -35, 0.25,
                           TimestampProvenance(timing_source="vad_region", alignment_method="vad_energy_or_neural",
                                               evidence_quality="medium_word", uncertainty_seconds=0.05))


def test_real_ffmpeg_tone_silence_accuracy_and_temp_sidecars(tmp_path):
    wav = _silence_tone_wav(tmp_path / "tone_gaps.wav")
    profile = AcousticProfiler().profile(wav)
    assert len(profile.silences) == 2
    for silence, expected in zip(profile.silences, ((1.5, 2.5), (4.5, 5.5))):
        assert silence.start_seconds == pytest.approx(expected[0], abs=0.05)
        assert silence.end_seconds == pytest.approx(expected[1], abs=0.05)
    assert len(profile.speech_intervals) == 3
    assert profile.energy_profile
    assert profile.timing_provenance.confidence is None
    assert not list(tmp_path.glob("*.silence.json"))


def test_real_ffmpeg_continuous_tone_zero_silence_branch(tmp_path):
    wav = _continuous_tone_wav(tmp_path / "continuous.wav")
    profile = AcousticProfiler().profile(wav)
    assert profile.silences == ()
    assert len(profile.speech_intervals) == 1
    assert profile.speech_intervals[0].start_seconds == 0.0
    assert profile.speech_intervals[0].end_seconds == pytest.approx(3.0, abs=0.15)
    assert not list(tmp_path.glob("*.silence.json"))


def test_real_ffmpeg_scene_detect_returns_only_interior_cut(tmp_path):
    video = tmp_path / "two_shots.mp4"
    _run_ffmpeg("-f", "lavfi", "-i", "color=c=red:s=320x240:r=25:d=2",
                "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25:d=2",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=4",
                "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
                "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(video))
    profile = AcousticProfiler().profile(video, video_path=video, include_energy=False)
    assert any(c.timestamp_seconds == pytest.approx(2.0, abs=0.25) for c in profile.shot_cuts)
    assert all(0 < c.timestamp_seconds < 4.0 for c in profile.shot_cuts)
    assert not list(tmp_path.glob("*.scenes.json"))


def test_incomplete_thought_never_snaps_dramatic_pauses():
    result = AcousticProfiler().suggest_boundary_refinement(
        2.0, 5.0, _profile_with_pauses(), thought_complete_start=False, thought_complete_end=False)
    assert (result.refined_start_seconds, result.refined_end_seconds) == (2.0, 5.0)
    assert not result.start_adjusted and not result.end_adjusted
    assert result.start_provenance.transformation == "raw_unmodified"


def test_thought_complete_boundaries_snap_with_padding_and_honest_provenance():
    result = AcousticProfiler().suggest_boundary_refinement(
        2.2, 4.7, _profile_with_pauses(), thought_complete_start=True, thought_complete_end=True,
        speech_padding_seconds=0.08)
    assert result.refined_start_seconds == pytest.approx(2.42)
    assert result.refined_end_seconds == pytest.approx(4.58)
    assert result.start_provenance.original_seconds == 2.2
    assert result.end_provenance.original_seconds == 4.7
    for provenance in (result.start_provenance, result.end_provenance):
        assert provenance.transformation == "silence_proximity_adjusted"
        assert provenance.confidence is None
        assert provenance.human_reviewed is False


def test_snap_inversion_is_aborted_and_reported():
    result = AcousticProfiler().suggest_boundary_refinement(
        2.2, 2.3, _profile_with_pauses(), thought_complete_start=True, thought_complete_end=True,
        speech_padding_seconds=0.08)
    assert (result.refined_start_seconds, result.refined_end_seconds) == (2.2, 2.3)
    assert not result.start_adjusted and not result.end_adjusted
    assert result.warnings == ("boundary snap aborted: would invert or collapse interval",)


@pytest.mark.parametrize("start,end,kwargs", [
    (float("nan"), 1.0, {}), (0.0, float("inf"), {}), (-1.0, 1.0, {}), (True, 1.0, {}),
    (0.0, 0.0, {}), (0.0, 1.0, {"max_snap_window_seconds": float("nan")}),
    (0.0, 1.0, {"speech_padding_seconds": -0.1}), (0.0, 1.0, {"min_pause_duration_seconds": True}),
])
def test_invalid_refinement_inputs_raise_value_error(start, end, kwargs):
    with pytest.raises(ValueError):
        AcousticProfiler().suggest_boundary_refinement(start, end, _profile_with_pauses(),
            thought_complete_start=True, thought_complete_end=True, **kwargs)


def test_missing_audio_is_typed_error(tmp_path):
    with pytest.raises(AcousticProfilingError, match="Audio file not found"):
        AcousticProfiler().profile(tmp_path / "missing.wav")


def test_silence_tool_claiming_output_without_json_fails_closed(tmp_path):
    wav = _continuous_tone_wav(tmp_path / "continuous.wav")

    class InconsistentTool:
        def execute(self, _inputs):
            return SimpleNamespace(success=True, data={"silence_segments": 1}, error=None)

    with pytest.raises(AcousticProfilingError, match="did not write its JSON output"):
        AcousticProfiler(silence_cutter=InconsistentTool(), audio_energy=object()).profile(
            wav, include_energy=False)


def test_optional_tools_degrade_gracefully_with_warnings(tmp_path):
    wav = _continuous_tone_wav(tmp_path / "continuous.wav")

    class FailedTool:
        def execute(self, _inputs):
            return SimpleNamespace(success=False, error="unavailable", data={})

    profile = AcousticProfiler(audio_energy=FailedTool(), scene_detect=FailedTool()).profile(
        wav, video_path=wav, include_energy=True, include_scene_cuts=True)
    assert profile.energy_profile == () and profile.shot_cuts == ()
    assert any("AudioEnergy unavailable" in warning for warning in profile.warnings)
    assert any("SceneDetect unavailable" in warning for warning in profile.warnings)


def test_vad_protocol_can_be_injected_without_silencecutter(tmp_path):
    wav = _continuous_tone_wav(tmp_path / "continuous.wav")

    class FakeVad:
        def detect_speech_and_silence(self, _path, duration):
            silence = SilenceInterval(1.0, 1.2, 0.2, source="vad")
            speech = (SpeechInterval(0.0, 1.0, 1.0, source="vad"),
                      SpeechInterval(1.2, duration, duration - 1.2, source="vad"))
            return [silence], list(speech)

    class MustNotRun:
        def execute(self, _inputs):
            raise AssertionError("SilenceCutter should not run when VAD is injected")

    profile = AcousticProfiler(vad_detector=FakeVad(), silence_cutter=MustNotRun()).profile(
        wav, include_energy=False)
    assert profile.silences == (SilenceInterval(1.0, 1.2, 0.2, source="vad"),)
    assert profile.speech_intervals[0].source == "vad"


def test_profile_helpers_use_half_open_energy_buckets():
    base = _profile_with_pauses()
    profile = AcousticProfile(base.audio_path, base.video_path, base.total_duration_seconds, base.silences,
                              base.speech_intervals,
                              (EnergyBucket(0, -20, True), EnergyBucket(1, -120, False), EnergyBucket(2, -30, True)),
                              (), base.silence_threshold_db, base.min_silence_duration_seconds,
                              base.timing_provenance)
    assert profile.average_loudness_lufs(0.5, 2.5) == pytest.approx(-25)
    assert profile.average_loudness_lufs(1.0, 2.0) is None
    assert profile.is_in_silence(2.0) == profile.silences[0]
    assert profile.nearest_silence(3.0, 0.6) == profile.silences[0]
