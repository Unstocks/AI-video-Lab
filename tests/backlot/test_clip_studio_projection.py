"""Unit tests for FE-1 read-only Clip Studio projection in backlot.state."""

from __future__ import annotations

import json
from pathlib import Path

from backlot.state import load_board_state
from lib import layout_ranges


def test_non_clip_project_returns_none_for_clip_studio(tmp_path: Path):
    proj = tmp_path / "trailer-demo"
    proj.mkdir()
    (proj / "project.json").write_text(
        json.dumps({"title": "Trailer Demo", "pipeline_type": "trailer"}), encoding="utf-8"
    )
    state = load_board_state(proj)
    assert state["clip_studio"] is None


def test_clip_studio_projection_joins_plan_renders_layout_seam_qa_and_exports(tmp_path: Path):
    proj = tmp_path / "podcast-ep42"
    (proj / "artifacts").mkdir(parents=True)
    (proj / "renders").mkdir(parents=True)
    (proj / "exports").mkdir(parents=True)
    (proj / "source").mkdir(parents=True)
    (proj / "source" / "source_video.mp4").write_bytes(b"fake-src")

    plan = {
        "source_transcript_sha256": "abc123",
        "candidates": [
            {
                "candidate_id": "clip_01",
                "editorial_title": "Why AI Studios Win",
                "start_seconds": 120.0,
                "end_seconds": 165.0,
                "review_state": "HUMAN_APPROVED",
                "spoken_hook": {"text": "This changes everything.", "speaker": "Host"},
                "spoken_opening": "This changes everything.",
                "cold_viewer_audit": {
                    "subject_clear": True,
                    "entities_grounded": True,
                    "pronouns_resolved": True,
                    "payoff_complete": True,
                    "qualifiers_preserved": True,
                },
            },
            {
                "candidate_id": "clip_02",
                "editorial_title": "Pending Candidate",
                "start_seconds": 300.0,
                "end_seconds": 340.0,
                "review_state": "AWAITING_HUMAN",
            },
        ],
    }
    (proj / "artifacts" / "clip_selection_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (proj / "artifacts" / "script.json").write_text(
        json.dumps({"source_transcript_sha256": "abc123", "candidates": plan["candidates"]}),
        encoding="utf-8",
    )

    mp4 = proj / "renders" / "clip_01.mp4"
    mp4.write_bytes(b"fake-mp4")
    (proj / "renders" / "clip_01.ass").write_text(
        "[V4+ Styles]\nStyle: Default,Arial,64\nStyle: Seam,Arial,64\n", encoding="utf-8"
    )
    layout_ranges.write(
        mp4,
        [
            {"start": 0.0, "end": 12.0, "layout": "track"},
            {"start": 12.0, "end": 45.0, "layout": "split"},
        ],
        punch_ins=[3.5, 22.0],
    )

    (proj / "artifacts" / "final_review.json").write_text(
        json.dumps({
            "clip_reports": [
                {
                    "candidate_id": "clip_01",
                    "status": "pass",
                    "production_state": "QA_PASSED",
                    "technical_probe": {"resolution": "1080x1920", "codec": "h264", "pixel_format_ok": True},
                    "audio_spotcheck": {"integrated_lufs": -14.1, "true_peak_dbtp": -1.9},
                    "issues": [],
                }
            ]
        }),
        encoding="utf-8",
    )

    state = load_board_state(proj)
    cs = state["clip_studio"]
    assert cs is not None
    assert cs["source_video"] == "source/source_video.mp4"
    assert cs["plan_sha256_synced"] is True
    assert cs["approved_count"] == 1
    assert cs["awaiting_approval_count"] == 1
    assert cs["qa_passed_count"] == 1

    c1, c2 = cs["clips"]
    assert c1["candidate_id"] == "clip_01"
    assert c1["video_path"] == "renders/clip_01.mp4"
    assert c1["subtitle_path"] == "renders/clip_01.ass"
    assert c1["seam_subtitles_used"] is True
    assert [r["layout"] for r in c1["layout_ranges"]] == ["track", "split"]
    assert c1["punch_ins"] == [3.5, 22.0]
    assert c1["qa"]["integrated_lufs"] == -14.1
    assert c1["production_state"] == "QA_PASSED"

    assert c2["candidate_id"] == "clip_02"
    assert c2["video_path"] is None
    assert c2["review_state"] == "AWAITING_HUMAN"
    assert c2["production_state"] == "PLANNED"


def test_corrupt_json_fails_soft_without_raising(tmp_path: Path):
    proj = tmp_path / "broken-clip-proj"
    (proj / "artifacts").mkdir(parents=True)
    (proj / "renders").mkdir(parents=True)
    (proj / "artifacts" / "clip_selection_plan.json").write_text("{bad json", encoding="utf-8")
    mp4 = proj / "renders" / "orphan.mp4"
    mp4.write_bytes(b"mp4")
    layout_ranges.write(mp4, [{"start": 0.0, "end": 5.0, "layout": "track"}])

    state = load_board_state(proj)
    assert state["clip_studio"] is not None
    assert state["clip_studio"]["clips"][0]["candidate_id"] == "orphan"
