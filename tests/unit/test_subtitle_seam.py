"""Unit & real-FFmpeg tests for Phase 3 Seam Subtitles, Continuation-Word Merging, and Bundled Fonts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lib import layout_ranges
from lib.media_qa import MediaQAConfig, MediaQAInspector
from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig
from tools.subtitle.subtitle_gen import SubtitleGen


class TestContinuationWordMerging:
    def test_merges_whisper_leading_space_continuations(self):
        words = [
            {"word": " This", "start": 0.0, "end": 0.2},
            {"word": " anti", "start": 0.2, "end": 0.4},
            {"word": "-hero", "start": 0.4, "end": 0.7},
            {"word": " costs", "start": 0.7, "end": 1.0},
            {"word": " $20", "start": 1.0, "end": 1.2},
            {"word": ".50", "start": 1.2, "end": 1.5},
            {"word": " don", "start": 1.5, "end": 1.7},
            {"word": "'t", "start": 1.7, "end": 1.9},
        ]
        merged = SubtitleGen.merge_continuation_words(words)
        assert [w["word"] for w in merged] == ["This", "anti-hero", "costs", "$20.50", "don't"]
        assert merged[1]["start"] == 0.2 and merged[1]["end"] == 0.7
        assert merged[3]["start"] == 1.0 and merged[3]["end"] == 1.5
        assert merged[4]["start"] == 1.5 and merged[4]["end"] == 1.9

    def test_merges_stripped_suffix_tokens(self):
        words = [
            {"word": "AI", "start": 0.0, "end": 0.3},
            {"word": "'s", "start": 0.3, "end": 0.5},
            {"word": "future", "start": 0.5, "end": 0.9},
            {"word": "!", "start": 0.9, "end": 1.0},
        ]
        merged = SubtitleGen.merge_continuation_words(words)
        assert [w["word"] for w in merged] == ["AI's", "future!"]
        assert merged[0]["end"] == 0.5
        assert merged[1]["end"] == 1.0


class TestStyleSeamAssGeneration:
    def test_style_seam_emitted_and_survives_neon_glow_reset_tags(self, tmp_path: Path):
        ass_path = tmp_path / "seam_test.ass"
        segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "Welcome to the show",
                "words": [
                    {"word": "Welcome", "start": 0.1, "end": 0.6},
                    {"word": "to", "start": 0.6, "end": 0.9},
                    {"word": "the", "start": 0.9, "end": 1.2},
                    {"word": "show", "start": 1.2, "end": 1.8},
                ],
            },
            {
                "start": 2.5,
                "end": 5.0,
                "text": "Both speakers talk here",
                "words": [
                    {"word": "Both", "start": 2.5, "end": 3.1},
                    {"word": "speakers", "start": 3.1, "end": 3.8},
                    {"word": "talk", "start": 3.8, "end": 4.3},
                    {"word": "here", "start": 4.3, "end": 4.9},
                ],
            },
        ]

        res = SubtitleGen().execute({
            "segments": segments,
            "format": "ass",
            "style_preset": "neon_glow",
            "highlight_style": "karaoke",
            "layout_ranges": [
                {"start": 0.0, "end": 2.0, "layout": "track"},
                {"start": 2.0, "end": 6.0, "layout": "split"},
            ],
            "output_path": str(ass_path),
        })
        assert res.success, res.error
        text = ass_path.read_text(encoding="utf-8")

        # Dedicated Style: Seam row with Alignment=5 (middle-center) and MarginV=0
        seam_styles = [ln for ln in text.splitlines() if ln.startswith("Style: Seam,")]
        assert len(seam_styles) == 1
        fields = seam_styles[0].split(",")
        assert fields[18] == "5"  # Alignment = 5 (middle-center)
        assert fields[21] == "0"  # MarginV = 0

        # Active-word {\r\blur...} resets stay locked to Style: Seam during [2.0, 6.0]
        dialogues = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
        default_lines = [ln for ln in dialogues if ",Default,," in ln]
        seam_lines = [ln for ln in dialogues if ",Seam,," in ln]
        assert len(default_lines) >= 1
        assert len(seam_lines) >= 1
        assert any("\\r" in ln for ln in seam_lines)

    def test_no_style_seam_when_no_split_ranges(self, tmp_path: Path):
        ass_path = tmp_path / "no_seam.ass"
        res = SubtitleGen().execute({
            "segments": [{"start": 0.0, "end": 1.5, "text": "Hello world"}],
            "format": "ass",
            "layout_ranges": [{"start": 0.0, "end": 2.0, "layout": "track"}],
            "output_path": str(ass_path),
        })
        assert res.success
        assert "Style: Seam," not in ass_path.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
def test_stacked_split_neon_glow_hinglish_render_and_qa_pass(tmp_path: Path):
    """End-to-end Phase 3 gate: stacked_split + neon_glow + Hinglish/Devanagari + bundled fonts + QA_PASSED."""
    src = tmp_path / "two_speaker_hinglish.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
            "-f", "lavfi", "-i", "aevalsrc='0.35*(0.55+0.45*sin(2*PI*1.5*t))*sin(2*PI*280*t)':s=48000:d=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )

    segments = [
        {
            "start": 0.2,
            "end": 3.8,
            "text": "Ye AI studio कमाल है!",
            "words": [
                {"word": " Ye", "start": 0.2, "end": 0.8},
                {"word": " AI", "start": 0.8, "end": 1.4},
                {"word": " studio", "start": 1.4, "end": 2.1},
                {"word": " कमाल", "start": 2.1, "end": 3.0},
                {"word": " है", "start": 3.0, "end": 3.6},
                {"word": "!", "start": 3.6, "end": 3.8},
            ],
        }
    ]

    composer = VerticalClipComposer()
    out_dir = tmp_path / "renders"
    res = composer.render_clip(
        candidate_id="hinglish_split_01",
        source_video_path=src,
        start_seconds=0.0,
        end_seconds=4.0,
        output_dir=out_dir,
        transcript_segments=segments,
        config=VerticalRenderConfig(
            layout_mode="stacked_split",
            style_preset="neon_glow",
            highlight_style="karaoke",
            codec="auto",
        ),
    )
    assert res.success, res.error
    out_mp4 = Path(res.output_video_path)
    out_ass = Path(res.subtitle_path)
    assert out_mp4.is_file() and out_ass.is_file()

    # Sidecar promoted alongside final clip
    sidecar_ranges = layout_ranges.read(out_mp4)
    assert sidecar_ranges and sidecar_ranges[0]["layout"] == "split"

    # ASS used Style: Seam and merged punctuation cleanly ("है!")
    ass_text = out_ass.read_text(encoding="utf-8")
    assert "Style: Seam," in ass_text
    assert ",Seam,," in ass_text
    assert "है!" in ass_text

    # MediaQAInspector passes broadcast QA
    qa = MediaQAInspector().inspect_clip(
        candidate_id="hinglish_split_01",
        video_path=out_mp4,
        subtitle_path=out_ass,
        expected_duration_seconds=4.0,
        locked_runtime="ffmpeg",
        config=MediaQAConfig(profile_name="youtube_shorts", require_subtitles=True),
    )
    assert qa.production_state == "QA_PASSED", f"QA failed: {qa.issues} / {qa.check_statuses}"
