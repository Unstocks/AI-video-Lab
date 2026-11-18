"""Unit tests for Phase 5 (MediaQA broadcast LUFS/true-peak metrics, ExportBundle gates, LLMGateway)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from lib.ffmpeg_profiles import METADATA_SCRUB, QUALITY, audio_encode_args, video_encode_args
from lib.llm_gateway import LLMGateway, extract_json_payload
from lib.media_qa import MediaQAConfig, MediaQAInspector
from tools.publishers.export_bundle import ExportBundle


class _DemoSchema(BaseModel):
    title: str
    score: int


class TestLLMGateway:
    def test_extract_json_payload_handles_raw_fenced_and_prose(self):
        assert extract_json_payload('{"title": "A", "score": 5}') == {"title": "A", "score": 5}
        assert extract_json_payload("Here it is:\n```json\n{\"title\": \"B\", \"score\": 4}\n```") == {
            "title": "B",
            "score": 4,
        }
        assert extract_json_payload('Sure! {"title": "C", "score": 3} Hope that helps.') == {
            "title": "C",
            "score": 3,
        }

    def test_progressive_fallback_json_schema_to_json_object_to_plain_text(self):
        calls = []

        class FakeCompletions:
            def create(self, **kwargs):
                calls.append(kwargs.get("response_format"))
                if len(calls) < 3:
                    raise RuntimeError("response_format unsupported by backend")
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content='```json\n{"title": "Win", "score": 5}\n```')
                        )
                    ]
                )

        fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
        gw = LLMGateway(client=fake_client)
        result = gw.complete_structured(
            system_prompt="Return JSON",
            user_prompt="Score this",
            response_model=_DemoSchema,
        )
        assert result == _DemoSchema(title="Win", score=5)
        assert calls[0]["type"] == "json_schema"
        assert calls[1]["type"] == "json_object"
        assert calls[2] is None


class TestPhase5BroadcastQaAndExportGates:
    @pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
    def test_media_qa_exposes_exact_lufs_and_true_peak_and_strict_gates(self, tmp_path: Path):
        out = tmp_path / "broadcast_clip.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=4",
                "-f", "lavfi", "-i", "aevalsrc='0.35*(0.55+0.45*sin(2*PI*1.5*t))*sin(2*PI*280*t)':s=48000:d=4",
                *video_encode_args(QUALITY, codec="auto"),
                *audio_encode_args(normalize=True),
                *METADATA_SCRUB,
                "-movflags", "+faststart",
                str(out),
            ],
            check=True,
            capture_output=True,
            timeout=60,
        )
        qa = MediaQAInspector().inspect_clip(
            candidate_id="bc_01",
            video_path=out,
            expected_duration_seconds=4.0,
            locked_runtime="ffmpeg",
            config=MediaQAConfig(
                profile_name="youtube_shorts",
                enforce_loudnorm_window=True,
                verify_metadata_scrubbed=True,
            ),
        )
        assert qa.production_state == "QA_PASSED", f"Issues: {qa.issues} / {qa.check_statuses}"
        assert "integrated_lufs" in qa.audio_spotcheck
        assert -16.5 <= qa.audio_spotcheck["integrated_lufs"] <= -11.5
        assert "true_peak_dbtp" in qa.audio_spotcheck
        assert qa.audio_spotcheck["true_peak_dbtp"] <= -1.0

    def test_export_bundle_blocks_batch_without_valid_final_review(self, tmp_path: Path):
        fake_vid = tmp_path / "clip.mp4"
        fake_vid.write_bytes(b"mp4")
        res = ExportBundle().execute({
            "clips": [{"clip_id": "clip_01", "video_path": str(fake_vid), "title": "Test"}],
            "export_dir": str(tmp_path / "exports"),
        })
        assert not res.success
        assert "final_review" in (res.error or "")
