"""Schema contract tests for the additive clip-selection dossier."""

from copy import deepcopy

import pytest
from jsonschema import ValidationError

from schemas.artifacts import ARTIFACT_NAMES, load_schema, validate_artifact
from tests.unit.test_evidence_models import valid_plan_payload


def test_valid_full_plan_accepts_unknown_nullable_evidence():
    payload = valid_plan_payload()
    assert payload["candidates"][0]["start_provenance"]["confidence"] is None
    assert payload["candidates"][0]["start_provenance"]["uncertainty_seconds"] is None
    validate_artifact("clip_selection_plan", payload)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(unexpected=True),
    lambda p: p["candidates"][0].update(validation_state="MAYBE"),
    lambda p: p.pop("project_id"),
])
def test_rejects_extra_enum_and_missing_required(mutate):
    payload = deepcopy(valid_plan_payload())
    mutate(payload)
    with pytest.raises(ValidationError):
        validate_artifact("clip_selection_plan", payload)


def test_existing_artifact_schemas_remain_registered_and_loadable():
    existing = [name for name in ARTIFACT_NAMES if name != "clip_selection_plan"]
    assert len(existing) == 20
    for name in existing:
        assert isinstance(load_schema(name), dict)


def test_schema_contract_bounds_and_nullable_speaker():
    schema = load_schema("clip_selection_plan")
    assert "version" in schema["required"]
    defs = schema["$defs"]
    assert defs["SpokenHookEvidence"]["properties"]["source_spans"]["minItems"] == 1
    assert defs["SpokenHookEvidence"]["properties"]["speaker"]["anyOf"]
    payload = valid_plan_payload()
    payload["candidates"][0]["spoken_hook"]["speaker"] = None
    payload["candidates"][0]["rejection_reason"] = None
    payload["candidates"][0]["duplicate_of_candidate_id"] = None
    validate_artifact("clip_selection_plan", payload)


