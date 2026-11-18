"""M4 reframe and subtitle behavior, including native FFmpeg output checks."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lib.media_profiles import YOUTUBE_SHORTS
from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig
from tools.base_tool import ToolResult
from tools.subtitle.subtitle_gen import SubtitleGen, rebase_segments_to_clip
from tools.video.auto_reframe import AutoReframe


def _run(args):
    return subprocess.run(args, capture_output=True, check=True, timeout=90)


def _probe(path):
    payload = json.loads(_run([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path),
    ]).stdout)
    return payload["streams"]


def test_youtube_shorts_profile_uses_180_second_limit():
    assert YOUTUBE_SHORTS.max_duration_seconds == 180
    assert (YOUTUBE_SHORTS.width, YOUTUBE_SHORTS.height) == (1080, 1920)


def test_shot_cut_smoothing_never_averages_across_boundary():
    tool = AutoReframe()
    values = [0.2, 0.2, 0.8, 0.8]
    timestamps = [1.0, 1.9, 2.0, 2.1]
    smooth = tool._smooth_positions_segmented(values, timestamps, [2.0], 5)
    assert smooth == values
    assert tool._smooth_positions_segmented(values, timestamps, [], 5) != values


def test_speaker_tracks_take_priority_and_only_active_tracks_are_used(tmp_path):
    tool = AutoReframe()
    face_file = tmp_path / "inactive-face-fixture.json"
    face_file.write_text(json.dumps({"faces": [
        {"timestamp_seconds": 0, "bbox": {"x": .05, "y": .2, "width": .1, "height": .2}},
    ]}), encoding="utf-8")
    try:
        selected = tool._get_face_data({
            "speaker_tracks": [{"timestamp_seconds": 1,
                                "bbox": {"x": .8, "y": .2, "width": .1, "height": .2},
                                "active": True}],
            "face_tracking_json": str(face_file),
        }, Path("unused.mp4"), 30)
        assert selected[0]["bbox"]["x"] == .8
    finally:
        face_file.unlink(missing_ok=True)
    rows = tool._normalize_tracks([
        {"timestamp_seconds": 0, "bbox": {"x": .05, "y": .2, "width": .1, "height": .2}, "active": False},
        {"timestamp_seconds": 1, "bbox": {"x": .8, "y": .2, "width": .1, "height": .2}, "active": True},
    ], 5)
    assert len(rows) == 1 and rows[0]["timestamp_seconds"] == 1
    tracks_path = Path("C:\\AI-Video-Lab\\tmp\\a'b.txt")
    escaped = tool._escape_ffmpeg_filter_path(tracks_path)
    assert "\\:" in escaped and "\\'" in escaped and "/" in escaped


def test_rebase_segments_supports_whisper_and_youtube_without_mutating_input():
    source = [
        {"text": "old", "start": 0.1, "duration": 0.5},
        {"text": "We learned this", "start": 1.0, "end": 3.2, "words": [
            {"word": "We", "start": .8, "end": 1.2},
            {"word": "learned", "start": 1.2, "end": 1.7},
            {"word": "this", "start": 3.0, "end": 3.5},
        ]},
        {"text": "later", "start": 4.1, "duration": .5},
    ]
    rebased = rebase_segments_to_clip(source, 1.0, 4.0)
    assert len(rebased) == 1
    assert rebased[0]["start"] == 0.0 and rebased[0]["end"] == 2.5
    assert rebased[0]["text"] == "We learned this"
    assert [w["start"] for w in rebased[0]["words"]] == pytest.approx([0.0, .2, 2.0])
    assert [w["end"] for w in rebased[0]["words"]] == pytest.approx([.2, .7, 2.5])
    assert source[1]["words"][0]["start"] == .8
    assert rebase_segments_to_clip([{"text": "Hello", "start": 2.0, "duration": 2.0}], 1.0, 3.0)[0] == {
        "text": "Hello", "start": 1.0, "end": 2.0,
    }


@pytest.mark.parametrize("start,end", [(-1, 2), (True, 2), (float("nan"), 2), (1, 1), (1, float("inf"))])
def test_rebase_rejects_invalid_clip_boundaries(start, end):
    with pytest.raises((TypeError, ValueError)):
        rebase_segments_to_clip([], start, end)


def test_ass_output_uses_mobile_safe_zones_centiseconds_and_unicode(tmp_path):
    output = tmp_path / "हिन्दी.ass"
    result = SubtitleGen().execute({
        "segments": [
            {"text": "क़िताब café 👨‍👩‍👧‍👦", "start": .999, "duration": 1.2},
            {"text": "Hinglish mein sach", "start": 2.2, "duration": .8},
        ],
        "format": "ass", "clip_start_seconds": 0, "output_path": str(output),
        "play_res_x": 1080, "play_res_y": 1920, "margin_v": 320,
    })
    assert result.success, result.error
    content = output.read_text(encoding="utf-8")
    assert "PlayResX: 1080" in content and "PlayResY: 1920" in content
    assert ",2,80,120,320,1" in content
    assert "0:00:01.00" in content
    assert "क़िताब café 👨‍👩‍👧‍👦" in content and "Hinglish mein sach" in content


def test_ass_text_escaping_and_karaoke_guard(tmp_path):
    output = tmp_path / "escape.ass"
    result = SubtitleGen().execute({
        "segments": [{"text": "{tag} \\ literal\nदूसरी पंक्ति", "start": 0, "duration": 2}],
        "format": "ass", "highlight_style": "karaoke", "output_path": str(output),
    })
    assert result.success, result.error
    assert result.data["effective_highlight_style"] == "none"
    assert "highlight_style downgraded to 'none': word-level timestamps unavailable" in result.data["warnings"]
    assert any("font 'Noto Sans Devanagari' was not found" in warning for warning in result.data["warnings"])
    content = output.read_text(encoding="utf-8")
    assert r"\{tag\}" in content and r"\\ literal\Nदूसरी पंक्ति" in content

    word_output = tmp_path / "word.ass"
    word_result = SubtitleGen().execute({
        "segments": [{"words": [{"word": "Hello", "start": 0, "end": .5},
                                {"word": "दुनिया", "start": .5, "end": 1.0}]}],
        "format": "ass", "highlight_style": "karaoke", "output_path": str(word_output),
    })
    assert word_result.success, word_result.error
    assert word_result.data["effective_highlight_style"] == "karaoke"
    assert r"{\kf50}Hello {\kf50}दुनिया" in word_output.read_text(encoding="utf-8")


def test_srt_output_rebases_episode_timestamps_to_clip_zero(tmp_path):
    output = tmp_path / "clip-relative.srt"
    result = SubtitleGen().execute({
        "segments": [{"text": "A later episode line", "start": 120.5, "duration": 2.0}],
        "format": "srt", "clip_start_seconds": 120.0, "clip_end_seconds": 124.0,
        "output_path": str(output),
    })
    assert result.success, result.error
    assert "00:00:00,500 --> 00:00:02,500" in output.read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
@pytest.mark.parametrize("layout", ["single_crop", "blurred_pillarbox", "stacked_split"])
def test_all_reframe_layouts_emit_mobile_compatible_video(tmp_path, layout):
    source = tmp_path / "source.mp4"
    output = tmp_path / f"{layout}.mp4"
    _run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=640x360:rate=10:duration=1", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(source),
    ])
    result = AutoReframe().execute({
        "input_path": str(source), "output_path": str(output),
        "target_width": 1080, "target_height": 1920, "layout_mode": layout,
    })
    assert result.success, result.error
    streams = _probe(output)
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert (video["codec_name"], video["pix_fmt"]) == ("h264", "yuv420p")
    assert audio["codec_name"] == "aac"


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_reframe_accepts_silent_video_with_optional_audio_mapping(tmp_path):
    source, output = tmp_path / "silent.mp4", tmp_path / "silent-vertical.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
          "color=c=black:size=320x180:rate=10:duration=0.5", "-c:v", "libx264", str(source)])
    result = AutoReframe().execute({
        "input_path": str(source), "output_path": str(output),
        "target_width": 1080, "target_height": 1920,
    })
    assert result.success, result.error
    assert next(stream for stream in _probe(output) if stream["codec_type"] == "video")["width"] == 1080


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_dynamic_crop_uses_track_timestamps_and_cleans_sendcmd_workspace(tmp_path):
    source, output = tmp_path / "moving.mp4", tmp_path / "moving-vertical.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
          "testsrc2=size=96x64:rate=10:duration=1", "-c:v", "libx264", str(source)])
    tracks = [
        {"timestamp_seconds": 0.0, "bbox": {"x": .15, "y": .2, "width": .1, "height": .2}, "active": True},
        {"timestamp_seconds": .4, "bbox": {"x": .65, "y": .2, "width": .1, "height": .2}, "active": True},
        {"timestamp_seconds": .8, "bbox": {"x": .15, "y": .2, "width": .1, "height": .2}, "active": True},
    ]
    result = AutoReframe().execute({
        "input_path": str(source), "output_path": str(output), "target_width": 48,
        "target_height": 64, "speaker_tracks": tracks, "smoothing_window": 1,
    })
    assert result.success, result.error
    assert result.data["method"] == "face_tracked"
    assert output.is_file()
    assert not list(tmp_path.glob(".reframe-*"))


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_vertical_composer_converts_vfr_input_to_cfr(tmp_path, monkeypatch):
    source = tmp_path / "variable-rate.mp4"
    _run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
        "testsrc2=size=320x180:rate=30:duration=2",
        "-vf", "select='eq(n,0)+eq(n,1)+eq(n,4)+eq(n,5)+eq(n,10)+eq(n,20)+eq(n,30)+eq(n,40)'",
        "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
    ])
    original_run = VerticalClipComposer._run_ffmpeg
    commands = []

    def observe(command, *, timeout):
        commands.append(list(command))
        return original_run(command, timeout=timeout)

    monkeypatch.setattr(VerticalClipComposer, "_run_ffmpeg", staticmethod(observe))
    result = VerticalClipComposer().render_clip(
        candidate_id="cfr", source_video_path=source, start_seconds=0, end_seconds=1.3,
        output_dir=tmp_path / "cfr", transcript_segments=[{"text": "Convert variable frame timing", "start": 0, "duration": 1.2}],
        config=VerticalRenderConfig(subtitle_format="srt", burn_subtitles=True),
    )
    assert result.success, result.error
    assert any("-fps_mode" in command and command[command.index("-fps_mode") + 1] == "cfr" for command in commands)
    assert Path(result.output_video_path).is_file()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_vertical_composer_nvenc_failure_retries_with_libx264(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
          "testsrc2=size=320x180:rate=10:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
    original_execute = AutoReframe.execute
    codecs = []

    def fail_nvenc(self, inputs):
        codecs.append(inputs.get("codec"))
        if inputs.get("codec") == "h264_nvenc":
            return ToolResult(success=False, error="synthetic NVENC unavailable")
        return original_execute(self, inputs)

    monkeypatch.setattr(AutoReframe, "execute", fail_nvenc)
    result = VerticalClipComposer().render_clip(
        candidate_id="nvenc-fallback", source_video_path=source, start_seconds=0, end_seconds=1,
        output_dir=tmp_path / "fallback", config=VerticalRenderConfig(codec="h264_nvenc", burn_subtitles=False),
    )
    assert result.success, result.error
    assert codecs == ["h264_nvenc", "libx264"]
    assert any("h264_nvenc failed during reframing" in warning for warning in result.warnings)
    video = next(stream for stream in _probe(Path(result.output_video_path)) if stream["codec_type"] == "video")
    assert (video["codec_name"], video["pix_fmt"]) == ("h264", "yuv420p")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_vertical_composer_render_failure_leaves_no_orphan_files(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    _run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
          "testsrc2=size=320x180:rate=10:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)])
    output_dir = tmp_path / "failed-render"

    def fail_burn(_command, *, timeout):
        raise RuntimeError("synthetic subtitle burn failure")

    monkeypatch.setattr(VerticalClipComposer, "_run_ffmpeg", staticmethod(fail_burn))
    result = VerticalClipComposer().render_clip(
        candidate_id="no-orphans", source_video_path=source, start_seconds=0, end_seconds=1,
        output_dir=output_dir, transcript_segments=[{"text": "Caption text", "start": 0, "duration": 1}],
        config=VerticalRenderConfig(subtitle_format="srt", burn_subtitles=True),
    )
    assert not result.success and "synthetic subtitle burn failure" in result.error
    assert not list(output_dir.glob("*.mp4"))
    assert not list(output_dir.glob("*.ass"))
    assert not list(output_dir.glob("*.srt"))
    assert not list(output_dir.glob(".*"))
