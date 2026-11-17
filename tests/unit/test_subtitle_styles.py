"""Designer ASS preset, Unicode, word-timing, and real FFmpeg integration tests."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from lib.subtitle_styles import (
    SUBTITLE_STYLE_PRESETS,
    SubtitleStylePreset,
    get_subtitle_style,
    hex_to_ass_color,
    list_subtitle_styles,
)
from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig
from tools.subtitle.subtitle_gen import SubtitleGen


WORD_SEGMENT = {
    "start": 10.0, "end": 13.0,
    "text": "We build a useful system today",
    "words": [
        {"word": "We", "start": 10.0, "end": 10.35},
        {"word": "build", "start": 10.35, "end": 10.75},
        {"word": "a", "start": 10.75, "end": 10.9},
        {"word": "useful", "start": 10.9, "end": 11.45},
        {"word": "system", "start": 11.45, "end": 12.1},
        {"word": "today", "start": 12.1, "end": 13.0},
    ],
}


def _ass(tmp_path: Path, preset: str, *, segment: dict | None = None, **extra):
    output = tmp_path / f"{preset}.ass"
    result = SubtitleGen().execute({
        "segments": [segment or WORD_SEGMENT], "clip_start_seconds": 10.0,
        "clip_end_seconds": 13.0, "format": "ass", "highlight_style": "karaoke",
        "style_preset": preset, "output_path": str(output), **extra,
    })
    assert result.success, result.error
    return output.read_text(encoding="utf-8"), result


def test_hex_to_ass_color_reverses_rgb_and_validates_inputs():
    assert hex_to_ass_color("#FF0000") == "&H000000FF"
    assert hex_to_ass_color("#00FF00") == "&H0000FF00"
    assert hex_to_ass_color("#0000FF") == "&H00FF0000"
    assert hex_to_ass_color("#FFD700") == "&H0000D7FF"
    assert hex_to_ass_color("#ff0000", alpha=128) == "&H800000FF"
    for bad_color in ("FF0000", "#FFF", "#GG0000", "#00000000", None):
        with pytest.raises(ValueError):
            hex_to_ass_color(bad_color)
    for bad_alpha in (-1, 256, True, 1.0, "0"):
        with pytest.raises(ValueError):
            hex_to_ass_color("#000000", alpha=bad_alpha)


def test_all_eight_presets_are_valid_immutable_and_have_safe_margins():
    assert len(list_subtitle_styles()) == 8
    assert list_subtitle_styles() == tuple(sorted(list(SUBTITLE_STYLE_PRESETS)))
    for name in list_subtitle_styles():
        preset = get_subtitle_style(name)
        assert isinstance(preset, SubtitleStylePreset)
        assert preset.margin_l >= 0 and preset.margin_r >= 0 and preset.margin_v >= 0
        for color in (preset.primary_color, preset.secondary_color, preset.outline_color, preset.back_color):
            assert len(color) == 10 and color.startswith("&H")
        with pytest.raises((AttributeError, TypeError)):
            preset.font_size = 10
    with pytest.raises(ValueError, match="available presets"):
        get_subtitle_style("unknown_style")
    assert get_subtitle_style("pill_highlight").border_style == 3
    assert get_subtitle_style("hinglish_impact").uppercase is False


def test_word_timed_presets_render_pop_glow_pill_and_unicode(tmp_path):
    hormozi, hormozi_result = _ass(tmp_path, "hormozi_pop")
    assert r"\t(0,80,\fscx118\fscy118)" in hormozi
    assert r"\c&H00E6FF&" in hormozi
    plain_hormozi = re.sub(r"\{[^}]*\}", "", hormozi)
    assert "WE BUILD A" in plain_hormozi and "USEFUL SYSTEM TODAY" in plain_hormozi
    assert hormozi_result.data["style_preset"] == "hormozi_pop"
    assert ",76," in next(line for line in hormozi.splitlines() if line.startswith("Style: Default"))

    neon, _ = _ass(tmp_path, "neon_glow")
    assert r"\blur3.5" in neon
    assert r"{\r\blur3.5}" in neon

    neon_wbw, _ = _ass(tmp_path, "neon_glow", highlight_style="word_by_word")
    assert r"{\blur3.5}WE" in neon_wbw

    pill, _ = _ass(tmp_path, "pill_highlight")
    pill_style = next(line for line in pill.splitlines() if line.startswith("Style: Default"))
    assert ",3,8,0," in pill_style
    assert "&H40000000" in pill_style

    doc, _ = _ass(tmp_path, "documentary_clean")
    doc_style = next(line for line in doc.splitlines() if line.startswith("Style: Default"))
    assert "&H80000000,&H80000000," in doc_style

    hindi_segment = {
        "start": 10.0, "end": 13.0, "text": "यह सच में काम करता है",
        "words": [
            {"word": "यह", "start": 10.0, "end": 10.4},
            {"word": "सच", "start": 10.4, "end": 10.8},
            {"word": "mein", "start": 10.8, "end": 11.2},
            {"word": "काम", "start": 11.2, "end": 11.7},
            {"word": "करता", "start": 11.7, "end": 12.3},
            {"word": "है", "start": 12.3, "end": 13.0},
        ],
    }
    hinglish, _ = _ass(tmp_path, "hinglish_impact", segment=hindi_segment)
    plain_hinglish = re.sub(r"\{[^}]*\}", "", hinglish)
    assert all(token in plain_hinglish for token in ("यह", "सच", "mein", "काम", "करता", "है"))
    assert "MEIN" not in plain_hinglish


def test_coarse_caption_presets_keep_honest_highlight_downgrade(tmp_path):
    segment = {"text": "No invented word timing please.", "start": 10.0, "end": 13.0}
    content, result = _ass(tmp_path, "hormozi_pop", segment=segment)
    assert result.data["effective_highlight_style"] == "none"
    assert any("word-level timestamps unavailable" in warning for warning in result.data["warnings"])
    assert "NO INVENTED WORD TIMING PLEASE." in content
    assert r"\kf" not in content


def test_legacy_ass_output_is_unchanged_when_style_preset_omitted(tmp_path):
    output = tmp_path / "legacy.ass"
    result = SubtitleGen().execute({
        "segments": [{"words": [{"word": "A & B", "start": 0, "end": 1}]}],
        "format": "ass", "highlight_style": "karaoke", "output_path": str(output),
    })
    assert result.success, result.error
    text = output.read_text(encoding="utf-8")
    assert "Style: Default,Noto Sans Devanagari,64,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000," in text
    assert "{\\kf100}A & B" in text
    assert "style_preset" not in result.data


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe required")
def test_real_vertical_composer_burns_preset_and_fontsdir(tmp_path, monkeypatch):
    source = tmp_path / "wide.mp4"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "color=c=0x368fc1:s=1920x1080:r=25:d=3", "-f", "lavfi", "-i",
        "sine=frequency=440:duration=3", "-t", "3", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
    ], check=True, capture_output=True, timeout=60)
    invalid = VerticalClipComposer().render_clip(
        candidate_id="bad-font-dir", source_video_path=source, start_seconds=0, end_seconds=3,
        output_dir=tmp_path / "invalid", transcript_segments=[WORD_SEGMENT],
        config=VerticalRenderConfig(style_preset="hormozi_pop", fonts_dir=str(tmp_path / "missing-fonts")),
    )
    assert not invalid.success and "fonts_dir" in (invalid.error or "")

    fonts = tmp_path / "fonts"
    fonts.mkdir()
    burn_words = [dict(word, start=word["start"] - 10, end=word["end"] - 10) for word in WORD_SEGMENT["words"]]
    burn_segment = {"start": 0.0, "end": 3.0, "text": WORD_SEGMENT["text"], "words": burn_words}
    observed_commands = []
    original = VerticalClipComposer._run_ffmpeg

    def observe(command, *, timeout):
        observed_commands.append(list(command))
        return original(command, timeout=timeout)

    monkeypatch.setattr(VerticalClipComposer, "_run_ffmpeg", staticmethod(observe))
    result = VerticalClipComposer().render_clip(
        candidate_id="preset-burn", source_video_path=source, start_seconds=0, end_seconds=3,
        output_dir=tmp_path / "renders", transcript_segments=[burn_segment],
        config=VerticalRenderConfig(style_preset="hormozi_pop", fonts_dir=str(fonts), subtitle_format="ass", highlight_style="karaoke"),
    )
    assert result.success, result.error
    assert Path(result.output_video_path).is_file()
    vf = next(command[index + 1] for command in observed_commands for index, value in enumerate(command) if value == "-vf")
    assert "fontsdir=" in vf
    assert "\\:" in vf
    ass_text = Path(result.subtitle_path).read_text(encoding="utf-8")
    assert r"\fscx118" in ass_text
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", result.output_video_path],
        check=True, capture_output=True, text=True, timeout=20,
    ).stdout)
    video = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    assert (video["width"], video["height"], video["codec_name"], video["pix_fmt"]) == (1080, 1920, "h264", "yuv420p")
