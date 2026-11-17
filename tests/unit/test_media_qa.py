"""Real FFmpeg coverage for deterministic post-render QA behavior."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from lib.media_qa import MediaQAConfig, MediaQAInspector
from schemas.artifacts import validate_artifact


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe required")


def _render(path: Path, *, video: str = "color=c=0x36a7d8:s=1080x1920:r=25:d=3", audio: str | None = "sine=frequency=440:duration=3") -> Path:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", video]
    if audio is not None:
        args += ["-f", "lavfi", "-i", audio]
    args += ["-t", "3", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio is not None:
        args += ["-c:a", "aac", "-shortest"]
    args += [str(path)]
    subprocess.run(args, check=True, capture_output=True, timeout=60)
    return path


def _probe(path: Path) -> dict:
    return json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout)


def test_valid_vertical_render_passes_with_subtitles(tmp_path):
    video = _render(tmp_path / "good.mp4")
    ass = tmp_path / "good.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\n[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.20,0:00:02.80,Default,,0,0,0,,A grounded caption\n",
        encoding="utf-8",
    )
    output_frames = tmp_path / "frames"
    temp_root = Path(tempfile.gettempdir())
    temp_before = set(temp_root.glob("media_qa_*"))
    report = MediaQAInspector().inspect_clip(
        candidate_id="good", video_path=video, expected_duration_seconds=3, subtitle_path=ass,
        frames_output_dir=output_frames, config=MediaQAConfig(require_subtitles=True),
    )
    assert report.status == "pass"
    assert report.production_state == "QA_PASSED"
    assert report.visual_spotcheck["frames_sampled"] == 4
    assert report.visual_spotcheck["black_frames_detected"] is False
    assert report.audio_spotcheck["narration_present"] is True
    assert report.subtitle_check["subtitles_present"] is True
    assert report.subtitle_check["timing_drift_detected"] is False
    validate_artifact("final_review", report.final_review_artifact)
    assert set(temp_root.glob("media_qa_*")) == temp_before
    shutil.rmtree(output_frames)
    assert not output_frames.exists()


def test_black_video_is_failed_and_schema_valid(tmp_path):
    video = _render(tmp_path / "black.mp4", video="color=c=black:s=1080x1920:r=25:d=3")
    report = MediaQAInspector().inspect_clip(candidate_id="black", video_path=video)
    assert report.visual_spotcheck["black_frames_detected"] is True
    assert report.status == "fail" and report.production_state == "QA_FAILED"
    validate_artifact("final_review", report.final_review_artifact)


def test_silent_and_missing_audio_fail(tmp_path):
    silent = _render(tmp_path / "silent.mp4", audio="anullsrc=channel_layout=stereo:sample_rate=48000")
    silent_report = MediaQAInspector().inspect_clip(candidate_id="silent", video_path=silent)
    assert silent_report.audio_spotcheck["unexpected_silence"] is True
    assert silent_report.audio_spotcheck["narration_present"] is False
    assert silent_report.production_state == "QA_FAILED"

    video_only = _render(tmp_path / "video_only.mp4", audio=None)
    no_audio = MediaQAInspector().inspect_clip(candidate_id="video-only", video_path=video_only)
    assert no_audio.technical_probe["has_audio"] is False
    assert no_audio.production_state == "QA_FAILED"


def test_audio_video_duration_drift_is_reported(tmp_path):
    video = tmp_path / "av-drift.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "color=c=0x36a7d8:s=1080x1920:r=25:d=3", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=2", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
    ], check=True, capture_output=True, timeout=60)
    probe = _probe(video)
    video_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    audio_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")
    assert abs(float(video_stream["duration"]) - float(audio_stream["duration"])) > .25
    report = MediaQAInspector().inspect_clip(candidate_id="av-drift", video_path=video)
    assert any("duration drift" in issue for issue in report.technical_probe["issues"])
    assert report.production_state == "QA_FAILED"


def test_subtitle_drift_and_missing_video_are_schema_valid_failures(tmp_path):
    video = _render(tmp_path / "drift.mp4")
    ass = tmp_path / "drift.ass"
    ass.write_text(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:02:00.00,0:02:01.00,Default,,0,0,0,,Late cue\n", encoding="utf-8",
    )
    drift = MediaQAInspector().inspect_clip(candidate_id="drift", video_path=video, subtitle_path=ass)
    assert drift.subtitle_check["timing_drift_detected"] is True
    assert drift.production_state == "QA_FAILED"
    missing = MediaQAInspector().inspect_clip(candidate_id="missing", video_path=tmp_path / "absent.mp4")
    assert missing.production_state == "QA_FAILED"
    assert "frames_sampled" not in missing.visual_spotcheck
    validate_artifact("final_review", missing.final_review_artifact)


def test_runtime_swap_blocks_delivery(tmp_path):
    video = _render(tmp_path / "runtime.mp4")
    report = MediaQAInspector().inspect_clip(candidate_id="runtime", video_path=video, locked_runtime="remotion")
    assert report.promise_preservation["runtime_swap_detected"] is True
    assert report.status == "fail"
    assert report.recommended_action == "block"


def test_invalid_config_rejects_less_than_four_frames():
    with pytest.raises(ValueError, match="sample_frame_count"):
        MediaQAConfig(sample_frame_count=3)
