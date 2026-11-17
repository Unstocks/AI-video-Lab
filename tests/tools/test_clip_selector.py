"""BaseTool integration, artifact contracts, and clean error boundaries."""

import json
from pathlib import Path

from lib.models.clip_plan import ClipSelectionPlan
from schemas.artifacts import validate_artifact
from tools.analysis.clip_selector import ClipSelector
from tools.tool_registry import ToolRegistry


def audit(**overrides):
    value = {"subject_grounded": True, "entities_resolved": True, "pronouns_resolved": True,
             "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": True}
    value.update(overrides)
    return value


def candidate(candidate_id, *, hook="We learned this lesson the hard way", audit_payload=None, start=0, end=20, score=.9):
    return {
        "candidate_id": candidate_id, "start_seconds": start, "end_seconds": end,
        "original_spoken_dialogue": "We learned this lesson the hard way. The actual strategy was focus.",
        "spoken_opening": hook, "spoken_hook_text": hook, "editorial_title": f"Title {candidate_id}",
        "cold_viewer_audit": audit_payload or audit(),
        "editorial_scores": [{"dimension": "hook_pull", "rationale": "The opening claim is specific and source-grounded.", "score": score}],
    }


def inputs(**overrides):
    value = {
        "project_id": "test-project", "source_media_ref": "episode-1.mp4", "transcript_format": "youtube",
        "transcript": {"transcript": [{"text": "We learned this lesson the hard way. The actual strategy was focus.",
                                         "start": 0, "duration": 30}]},
        "candidates": [candidate("selected"),
                       candidate("hallucinated", hook="The team went viral overnight"),
                       candidate("cold", audit_payload=audit(pronouns_resolved=False, passed=False)),
                       candidate("duplicate", score=.8)],
        "generated_at": "2026-11-17T12:00:00Z",
    }
    value.update(overrides)
    return value


def test_tool_registry_discovers_offline_clip_selector_contract():
    registry = ToolRegistry()
    registry.discover()
    tool = registry.get("clip_selector")
    assert tool is not None
    assert tool.tier.value == "analyze"
    assert tool.capability == "analysis"
    assert tool.get_status().value == "available"
    assert tool.dependencies == []
    assert len(registry.list_all()) >= 166


def test_end_to_end_plan_and_provisional_script_are_schema_valid_and_atomic(tmp_path):
    result = ClipSelector().execute(inputs(output_dir=str(tmp_path)))
    assert result.success, result.error
    plan_path = tmp_path / "clip_selection_plan.json"
    script_path = tmp_path / "script.json"
    assert plan_path.is_file() and script_path.is_file()
    assert sorted(Path(p).name for p in result.artifacts) == [
        "clip_selection_plan.json", "script.json"]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    script = json.loads(script_path.read_text(encoding="utf-8"))
    validate_artifact("clip_selection_plan", plan)
    validate_artifact("script", script)
    assert script["metadata"]["approval_status"] == "provisional"
    assert script["metadata"]["clip_selection_plan_sha256"] == result.data["plan_sha256"]
    assert script["metadata"]["clip_selection_plan_sha256"] == ClipSelectionPlan.model_validate(plan).compute_plan_sha256()
    assert [section["id"] for section in script["sections"]] == ["selected"]
    by_id = {item["candidate_id"]: item for item in plan["candidates"]}
    assert by_id["hallucinated"]["validation_state"] == "INVALID_HOOK_PROVENANCE"
    assert by_id["cold"]["eligibility_state"] == "REJECTED_COLD_VIEWER"
    assert by_id["duplicate"]["eligibility_state"] == "DEFERRED_DUPLICATE"
    assert result.data["selected_count"] == 1


def test_zero_eligible_candidates_write_only_valid_plan_and_no_dummy_script(tmp_path):
    (tmp_path / "script.json").write_text('{"stale": true}', encoding="utf-8")
    result = ClipSelector().execute(inputs(candidates=[candidate("hallucinated", hook="Completely fabricated claim")],
                                           output_dir=str(tmp_path)))
    assert result.success, result.error
    assert result.data["status"] == "no_eligible_candidates"
    assert result.data["selected_count"] == 0
    assert result.data["provisional_script"] is None
    assert (tmp_path / "clip_selection_plan.json").is_file()
    assert not (tmp_path / "script.json").exists()
    assert not list(tmp_path.glob(".*.tmp"))
    validate_artifact("clip_selection_plan", result.data["plan"])


def test_custom_max_duration_uses_safe_preferred_default():
    result = ClipSelector().execute(inputs(max_duration_seconds=60.0))
    assert result.success, result.error


def test_invalid_project_id_malformed_transcript_and_empty_source_ref_return_tool_errors():
    tool = ClipSelector()
    for bad_inputs in (
        inputs(project_id="../evil"),
        inputs(transcript="not a youtube payload"),
        inputs(source_media_ref="  "),
    ):
        result = tool.execute(bad_inputs)
        assert result.success is False
        assert result.error
