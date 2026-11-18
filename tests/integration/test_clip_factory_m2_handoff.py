"""End-to-end proof for the clip-factory evidence and human approval handoff."""

import json

import pytest

from backlot.state import load_board_state
from lib.checkpoint import (
    CheckpointValidationError,
    get_next_stage,
    init_project,
    read_checkpoint,
    write_checkpoint,
)
from tools.analysis.clip_selector import (
    ClipSelector,
    finalize_approved_selection,
    verify_script_plan_sync,
)


def _candidate(candidate_id, text, start, end):
    return {
        "candidate_id": candidate_id,
        "start_seconds": start,
        "end_seconds": end,
        "original_spoken_dialogue": text,
        "spoken_opening": text,
        "spoken_hook_text": text,
        "editorial_title": f"Moment {candidate_id}",
        "editorial_framing": f"Why {candidate_id} matters",
        "cold_viewer_audit": {
            "subject_grounded": True,
            "entities_resolved": True,
            "pronouns_resolved": True,
            "premise_to_payoff_complete": True,
            "qualifiers_preserved": True,
            "passed": True,
        },
        "editorial_scores": [{
            "dimension": "hook_pull",
            "rationale": "Specific, self-contained and supported by the source.",
            "score": 0.9,
        }],
    }


def _save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def test_real_checkpoint_backlot_and_clip_selector_human_gate(tmp_path):
    project_id = "handoff-test"
    pipeline_dir = tmp_path / "projects"
    project_dir = init_project(project_id, title="Handoff test", pipeline_type="clip-factory",
                               pipeline_dir=pipeline_dir)
    brief = {
        "version": "1.0", "title": "Three moments", "hook": "A useful lesson",
        "key_points": ["Evidence", "Review"], "tone": "clear", "style": "clean-professional",
        "target_platform": "generic", "target_duration_seconds": 60,
    }
    write_checkpoint(pipeline_dir, project_id, "idea", "completed", {"brief": brief},
                     pipeline_type="clip-factory", human_approved=True)
    assert get_next_stage(pipeline_dir, project_id, "clip-factory") == "script"

    phrases = [
        "The first lesson is to measure the real problem.",
        "The second lesson is to test the smallest solution.",
        "The third lesson is to learn from every result.",
    ]
    transcript = {"transcript": [
        {"text": phrase, "start": start, "duration": 20}
        for phrase, start in zip(phrases, (0, 30, 60))
    ]}
    output_dir = project_dir / "artifacts"
    result = ClipSelector().execute({
        "project_id": project_id, "source_media_ref": "episode.mp4",
        "transcript": transcript, "transcript_format": "youtube",
        "candidates": [_candidate(f"c{i + 1}", phrase, start, start + 20)
                       for i, (phrase, start) in enumerate(zip(phrases, (0, 30, 60)))],
        "max_clips": 3, "generated_at": "2026-11-17T12:00:00Z",
        "output_dir": str(output_dir),
    })
    assert result.success, result.error
    provisional = result.data["provisional_script"]
    plan = result.data["plan"]
    assert provisional and provisional["metadata"]["approval_status"] == "provisional"
    assert (output_dir / "clip_selection_plan.json").exists()
    assert (output_dir / "script.json").exists()

    write_checkpoint(pipeline_dir, project_id, "script", "awaiting_human",
                     {"script": provisional, "clip_selection_plan": plan},
                     pipeline_type="clip-factory", human_approved=False)
    assert get_next_stage(pipeline_dir, project_id, "clip-factory") == "script"
    with pytest.raises(CheckpointValidationError, match="GATE VIOLATION"):
        write_checkpoint(pipeline_dir, project_id, "script", "completed",
                         {"script": provisional, "clip_selection_plan": plan},
                         pipeline_type="clip-factory", human_approved=False)
    with pytest.raises(CheckpointValidationError, match="approved, synchronized"):
        write_checkpoint(pipeline_dir, project_id, "script", "completed",
                         {"script": provisional, "clip_selection_plan": plan},
                         pipeline_type="clip-factory", human_approved=True)

    board = load_board_state(project_dir)
    assert board["artifacts"]["clip_selection_plan"]["version"] == "1.0"
    assert board["artifacts"]["script"]["metadata"]["approval_status"] == "provisional"
    script_rail = next(item for item in board["stages"] if item["name"] == "script")
    assert script_rail["status"] == "awaiting_human"
    assert script_rail["human_approved"] is False

    updated_plan, approved, updated_hash = finalize_approved_selection(
        plan,
        [
            {"candidate_id": "c1", "action": "approve", "review_metadata": "Approved as grounded."},
            {"candidate_id": "c2", "action": "revise_and_approve", "review_metadata": "Tighten opening.",
             "start_seconds": 31, "end_seconds": 50},
            {"candidate_id": "c3", "action": "reject", "rejection_reason": "Less distinctive."},
        ],
        reviewed_at="2026-11-17T13:00:00Z", output_dir=output_dir,
    )
    assert approved is not None
    assert approved["metadata"]["approval_status"] == "approved"
    assert approved["metadata"]["clip_selection_plan_sha256"] == updated_hash
    assert [section["id"] for section in approved["sections"]] == ["c1", "c2"]
    by_id = {candidate.candidate_id: candidate for candidate in updated_plan.candidates}
    revised = by_id["c2"]
    assert revised.start_provenance.transformation == "human_adjusted"
    assert revised.start_provenance.human_reviewed is True
    assert revised.start_provenance.original_seconds == 30
    assert revised.end_provenance.human_reviewed is True
    assert by_id["c3"].review_state == "HUMAN_REJECTED"
    verify_script_plan_sync(approved, updated_plan, require_approved=True)
    mutated = updated_plan.model_copy(update={
        "candidates": tuple(c.model_copy(update={"editorial_title": c.editorial_title + "!"})
                             if c.candidate_id == "c1" else c for c in updated_plan.candidates),
    })
    with pytest.raises(ValueError, match="SHA-256"):
        verify_script_plan_sync(approved, mutated, require_approved=True)

    write_checkpoint(pipeline_dir, project_id, "script", "completed",
                     {"script": approved, "clip_selection_plan": updated_plan.to_dict()},
                     pipeline_type="clip-factory", human_approved=True)
    assert read_checkpoint(pipeline_dir, project_id, "script")["status"] == "completed"
    assert get_next_stage(pipeline_dir, project_id, "clip-factory") == "scene_plan"

    scene_plan = {"version": "1.0", "scenes": [
        {"id": f"scene-{section['id']}", "type": "talking_head",
         "description": section["label"], "start_seconds": section["start_seconds"],
         "end_seconds": section["end_seconds"], "script_section_id": section["id"]}
        for section in approved["sections"]
    ]}
    write_checkpoint(pipeline_dir, project_id, "scene_plan", "completed", {"scene_plan": scene_plan},
                     pipeline_type="clip-factory", human_approved=True)
    board = load_board_state(project_dir)
    assert [scene["narration"] for scene in board["storyboard"]["scenes"]] == [
        section["text"] for section in approved["sections"]]
    scene_rail = next(item for item in board["stages"] if item["name"] == "scene_plan")
    assert scene_rail["gate_skipped"] is False
    assert json.loads((output_dir / "clip_selection_plan.json").read_text(encoding="utf-8"))["candidates"][0]["review_state"] == "HUMAN_APPROVED"
