"""Registered boundary for deterministic clip validation and selection."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import jsonschema
from pydantic import ValidationError as PydanticValidationError

from lib.acoustic_profiler import AcousticProfiler, AcousticProfilingError
from lib.conversation_structure import ConversationStructureAnalyzer
from lib.cold_viewer_auditor import ColdViewerAuditor
from lib.deduplicator import ClipDeduplicator
from lib.editorial_evaluator import CandidateProposal, EditorialEvaluator
from lib.models.clip_plan import ClipSelectionPlan, ColdViewerAudit, EditorialCriterionScore
from lib.models.transcript import RawTranscriptDocument, SourceSpan, TimestampProvenance
from lib.transcript_normalizer import TranscriptNormalizer
from schemas.artifacts import validate_artifact
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


_PROJECT_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


def _timestamp(value: object) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str):
        raise TypeError("generated_at must be an ISO-8601 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("generated_at must be a valid ISO-8601 timestamp") from exc
    return value


def _proposal(payload: dict[str, Any]) -> CandidateProposal:
    data = dict(payload)
    data["cold_viewer_audit"] = ColdViewerAudit.model_validate(data["cold_viewer_audit"])
    data["spoken_opening_spans"] = tuple(SourceSpan.model_validate(span) for span in data.get("spoken_opening_spans", ()))
    if data.get("spoken_hook_spans") is not None:
        data["spoken_hook_spans"] = tuple(SourceSpan.model_validate(span) for span in data["spoken_hook_spans"])
    data["editorial_scores"] = tuple(EditorialCriterionScore.model_validate(score)
                                     for score in data.get("editorial_scores", ()))
    for key in ("start_provenance", "end_provenance"):
        if data.get(key) is not None:
            data[key] = TimestampProvenance.model_validate(data[key])
    return CandidateProposal(**data)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _as_plan(plan: ClipSelectionPlan | dict[str, Any]) -> ClipSelectionPlan:
    return plan if isinstance(plan, ClipSelectionPlan) else ClipSelectionPlan.from_dict(plan)


def build_script_from_plan(
    plan: ClipSelectionPlan | dict[str, Any], *,
    approval_status: Literal["provisional", "approved"],
    title: Optional[str] = None,
    plan_ref: str = "clip_selection_plan.json",
) -> Optional[dict[str, Any]]:
    """Build the schema-valid script view from the authoritative clip plan."""
    plan = _as_plan(plan)
    if approval_status not in ("provisional", "approved"):
        raise ValueError("approval_status must be provisional or approved")
    expected_state = "SELECTED_FOR_REVIEW" if approval_status == "provisional" else "HUMAN_APPROVED"
    selected = [candidate for candidate in plan.candidates
                if candidate.validation_state == "VALID"
                and candidate.eligibility_state == "ELIGIBLE"
                and candidate.review_state == expected_state]
    if approval_status == "approved":
        for candidate in selected:
            if not candidate.human_reviewed_at or not candidate.review_metadata:
                raise ValueError(f"approved candidate {candidate.candidate_id} lacks human review metadata")
    if not selected:
        return None
    result = {
        "version": "1.0",
        "title": title or plan.source_media_ref,
        "total_duration_seconds": round(sum(c.duration_seconds for c in selected), 3),
        "sections": [{
            "id": c.candidate_id, "label": c.editorial_title,
            "text": c.original_spoken_dialogue,
            "start_seconds": c.start_seconds, "end_seconds": c.end_seconds,
            "source_ref": plan.source_media_ref,
        } for c in selected],
        "metadata": {
            "approval_status": approval_status,
            "clip_selection_plan_ref": plan_ref,
            "clip_selection_plan_sha256": plan.compute_plan_sha256(),
            "transcript_revision_id": plan.transcript_revision_id,
            "selected_candidate_ids": [c.candidate_id for c in selected],
            "source_media_ref": plan.source_media_ref,
        },
    }
    validate_artifact("script", result)
    return result


def finalize_approved_selection(
    plan: ClipSelectionPlan | dict[str, Any], decisions: Sequence[dict[str, Any]], *,
    reviewed_at: str, title: Optional[str] = None,
    output_dir: Optional[str | Path] = None,
) -> tuple[ClipSelectionPlan, Optional[dict[str, Any]], str]:
    """Apply human decisions and regenerate the synchronized approved script."""
    current = _as_plan(plan)
    if not isinstance(reviewed_at, str) or not reviewed_at.strip():
        raise ValueError("reviewed_at must be a non-empty timestamp")
    by_id = {candidate.candidate_id: candidate for candidate in current.candidates}
    updated = dict(by_id)
    seen: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("each review decision must be an object")
        candidate_id = decision.get("candidate_id")
        action = decision.get("action")
        if candidate_id not in by_id:
            raise ValueError(f"unknown candidate_id: {candidate_id}")
        if candidate_id in seen:
            raise ValueError(f"duplicate decision for candidate_id: {candidate_id}")
        seen.add(candidate_id)
        candidate = by_id[candidate_id]
        metadata = decision.get("review_metadata")
        if action in ("approve", "revise_and_approve"):
            if candidate.validation_state != "VALID" or candidate.eligibility_state != "ELIGIBLE":
                raise ValueError(f"candidate {candidate_id} is not valid and eligible")
            if not isinstance(metadata, str) or not metadata.strip():
                raise ValueError(f"{action} requires non-empty review_metadata")
            if action == "approve":
                updated[candidate_id] = candidate.model_copy(update={
                    "review_state": "HUMAN_APPROVED", "human_reviewed_at": reviewed_at,
                    "review_metadata": metadata,
                    "start_provenance": candidate.start_provenance.model_copy(update={"human_reviewed": True}),
                    "end_provenance": candidate.end_provenance.model_copy(update={"human_reviewed": True}),
                })
            else:
                start = decision.get("start_seconds", candidate.start_seconds)
                end = decision.get("end_seconds", candidate.end_seconds)
                if (isinstance(start, bool) or isinstance(end, bool)
                        or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                        or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start):
                    raise ValueError("revised boundaries must be finite, nonnegative, and end > start")
                start_changed, end_changed = start != candidate.start_seconds, end != candidate.end_seconds
                start_prov = candidate.start_provenance.model_copy(update={
                    "transformation": "human_adjusted", "human_reviewed": True,
                    "original_seconds": candidate.start_provenance.original_seconds
                    if candidate.start_provenance.original_seconds is not None
                    else (candidate.start_seconds if start_changed else None),
                })
                end_prov = candidate.end_provenance.model_copy(update={
                    "transformation": "human_adjusted", "human_reviewed": True,
                    "original_seconds": candidate.end_provenance.original_seconds
                    if candidate.end_provenance.original_seconds is not None
                    else (candidate.end_seconds if end_changed else None),
                })
                updated[candidate_id] = candidate.model_copy(update={
                    "start_seconds": float(start), "end_seconds": float(end),
                    "duration_seconds": float(end - start), "start_provenance": start_prov,
                    "end_provenance": end_prov,
                    "editorial_title": decision.get("editorial_title", candidate.editorial_title),
                    "editorial_framing": decision.get("editorial_framing", candidate.editorial_framing),
                    "review_state": "HUMAN_APPROVED", "human_reviewed_at": reviewed_at,
                    "review_metadata": metadata,
                })
        elif action == "reject":
            updated[candidate_id] = candidate.model_copy(update={
                "review_state": "HUMAN_REJECTED", "human_reviewed_at": reviewed_at,
                "review_metadata": metadata or "human_rejected",
                "rejection_reason": decision.get("rejection_reason") or candidate.rejection_reason,
            })
        else:
            raise ValueError(f"unsupported review action: {action}")
    updated_plan = current.model_copy(update={
        "candidates": tuple(updated[c.candidate_id] for c in current.candidates),
    })
    updated_dict = updated_plan.to_dict()
    validate_artifact("clip_selection_plan", updated_dict)
    updated_sha256 = updated_plan.compute_plan_sha256()
    approved_script = build_script_from_plan(updated_plan, approval_status="approved", title=title)
    if output_dir is not None:
        destination = Path(output_dir)
        _atomic_json(destination / "clip_selection_plan.json", updated_dict)
        script_path = destination / "script.json"
        if approved_script is None:
            script_path.unlink(missing_ok=True)
        else:
            _atomic_json(script_path, approved_script)
    return updated_plan, approved_script, updated_sha256


def verify_script_plan_sync(
    script: dict[str, Any], plan: ClipSelectionPlan | dict[str, Any], *, require_approved: bool = True,
) -> None:
    """Raise ValueError unless script metadata and sections agree with the plan."""
    plan = _as_plan(plan)
    validate_artifact("clip_selection_plan", plan.to_dict())
    validate_artifact("script", script)
    metadata = script.get("metadata") or {}
    expected_hash = plan.compute_plan_sha256()
    if metadata.get("clip_selection_plan_sha256") != expected_hash:
        raise ValueError("script and clip_selection_plan SHA-256 do not match")
    if metadata.get("transcript_revision_id") != plan.transcript_revision_id:
        raise ValueError("script and clip_selection_plan transcript revisions do not match")
    status = metadata.get("approval_status")
    if require_approved and status != "approved":
        raise ValueError("script is not approved")
    if not require_approved and status not in ("provisional", "approved"):
        raise ValueError("script approval_status must be provisional or approved")
    by_id = {candidate.candidate_id: candidate for candidate in plan.candidates}
    for section in script["sections"]:
        candidate = by_id.get(section["id"])
        if candidate is None:
            raise ValueError(f"script section {section['id']} is missing from clip_selection_plan")
        if require_approved and (candidate.validation_state != "VALID"
                                 or candidate.eligibility_state != "ELIGIBLE"
                                 or candidate.review_state != "HUMAN_APPROVED"):
            raise ValueError(f"script section {section['id']} is not an approved eligible candidate")
        if section["start_seconds"] != candidate.start_seconds or section["end_seconds"] != candidate.end_seconds:
            raise ValueError(f"script section {section['id']} timestamps do not match the plan")


class ClipSelector(BaseTool):
    name = "clip_selector"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies: list[str] = []
    capabilities = ["clip_selection", "hook_validation", "cold_viewer_audit", "clip_deduplication"]
    input_schema = {
        "type": "object",
        "required": ["project_id", "source_media_ref", "transcript", "candidates"],
        "properties": {
            "project_id": {"type": "string", "pattern": "^[a-zA-Z0-9_-]+$"},
            "source_media_ref": {"type": "string", "minLength": 1},
            "transcript": {"oneOf": [{"type": "object"}, {"type": "string"}]},
            "transcript_format": {"type": "string", "enum": ["youtube", "whisper", "srt", "vtt", "raw_document"], "default": "youtube"},
            "candidates": {"type": "array", "items": {"type": "object"}},
            "title": {"type": "string"}, "audio_path": {"type": "string"},
            "video_path": {"type": "string"}, "output_dir": {"type": "string"},
            "max_clips": {"type": "integer", "minimum": 0},
            "min_duration_seconds": {"type": "number", "minimum": 0},
            "max_duration_seconds": {"type": "number", "exclusiveMinimum": 0},
            "preferred_max_duration_seconds": {"type": "number", "exclusiveMinimum": 0},
            "temporal_iou_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            "semantic_similarity_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            "opening_window_seconds": {"type": "number", "minimum": 0},
            "require_hook_in_opening_window": {"type": "boolean"},
            "generated_at": {"type": "string"},
        },
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "required": ["status", "selected_count", "eligible_count", "rejected_count", "provisional_script", "plan", "warnings"],
        "properties": {
            "status": {"type": "string", "enum": ["completed", "no_eligible_candidates"]},
            "selected_count": {"type": "integer", "minimum": 0},
            "eligible_count": {"type": "integer", "minimum": 0},
            "rejected_count": {"type": "integer", "minimum": 0},
            "provisional_script": {"type": ["object", "null"]},
            "plan": {"type": "object"}, "plan_sha256": {"type": "string"},
            "warnings": {"type": "array", "items": {"type": "string"}},
            "surplus_count": {"type": "integer", "minimum": 0},
            "duplicate_count": {"type": "integer", "minimum": 0},
        },
        "additionalProperties": False,
    }
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=False)
    retry_policy = RetryPolicy(max_retries=0, retryable_errors=[])
    idempotency_key_fields = ["project_id", "source_media_ref", "candidates", "transcript_format", "max_clips"]
    side_effects = ["optionally writes clip_selection_plan.json and provisional script.json to output_dir"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            project_id = inputs["project_id"]
            if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
                raise ValueError("project_id must match ^[a-zA-Z0-9_-]+$")
            source_media_ref = inputs["source_media_ref"]
            if not isinstance(source_media_ref, str) or not source_media_ref.strip():
                raise ValueError("source_media_ref must be non-empty")
            transcript_format = inputs.get("transcript_format", "youtube")
            raw_transcript = inputs["transcript"]
            normalizer = TranscriptNormalizer()
            if transcript_format == "raw_document" and isinstance(raw_transcript, dict):
                raw_transcript = RawTranscriptDocument.model_validate(raw_transcript)
            normalized = normalizer.ingest_and_normalize(raw_transcript, transcript_format)
            topology = ConversationStructureAnalyzer().analyze(normalized)
            proposals = tuple(_proposal(item) for item in inputs["candidates"])

            acoustic_profile = None
            audio_path = inputs.get("audio_path") or inputs.get("video_path")
            video_path = inputs.get("video_path")
            if audio_path:
                acoustic_profile = AcousticProfiler().profile(audio_path, video_path=video_path)

            max_duration = inputs.get("max_duration_seconds", 120.0)
            preferred_max_duration = inputs.get("preferred_max_duration_seconds", min(90.0, max_duration))
            evaluator = EditorialEvaluator(
                min_duration_seconds=inputs.get("min_duration_seconds", 15.0),
                max_duration_seconds=max_duration,
                preferred_max_duration_seconds=preferred_max_duration,
                opening_window_seconds=inputs.get("opening_window_seconds", 5.0),
                require_hook_in_opening_window=inputs.get("require_hook_in_opening_window", False),
            )
            evaluated = evaluator.evaluate_candidates(proposals, normalized, topology=topology,
                                                       acoustic_profile=acoustic_profile)
            deduplicator = ClipDeduplicator(
                temporal_iou_threshold=inputs.get("temporal_iou_threshold", 0.35),
                semantic_similarity_threshold=inputs.get("semantic_similarity_threshold", 0.70),
            )
            deduped = deduplicator.deduplicate_and_select(
                [candidate.clip for candidate in evaluated.eligible_ranked], max_clips=inputs.get("max_clips"))
            candidates = (*deduped.selected, *deduped.surplus_pending, *deduped.deferred_duplicates,
                          *(candidate.clip for candidate in evaluated.rejected))
            generated_at = _timestamp(inputs.get("generated_at"))
            plan = ClipSelectionPlan(
                version="1.0", project_id=project_id, source_media_ref=source_media_ref,
                transcript_revision_id=normalized.raw_document.transcript_revision_id or "",
                generated_at=generated_at, candidates=tuple(candidates),
            )
            plan_data = plan.to_dict()
            validate_artifact("clip_selection_plan", plan_data)
            plan_sha256 = plan.compute_plan_sha256()
            selected = deduped.selected
            provisional_script = build_script_from_plan(
                plan, approval_status="provisional", title=inputs.get("title"))

            artifacts: list[str] = []
            output_dir = inputs.get("output_dir")
            if output_dir:
                destination = Path(output_dir)
                destination.mkdir(parents=True, exist_ok=True)
                plan_path = destination / "clip_selection_plan.json"
                _atomic_json(plan_path, plan_data)
                artifacts.append(str(plan_path))
                if provisional_script is not None:
                    script_path = destination / "script.json"
                    _atomic_json(script_path, provisional_script)
                    artifacts.append(str(script_path))
                else:
                    (destination / "script.json").unlink(missing_ok=True)

            warnings = [*evaluated.warnings]
            warnings.extend(warning for candidate in (*evaluated.eligible_ranked, *evaluated.rejected)
                            for warning in candidate.warnings)
            status = "completed" if selected else "no_eligible_candidates"
            data = {
                "status": status,
                "selected_count": len(selected),
                "eligible_count": len(evaluated.eligible_ranked),
                "rejected_count": len(evaluated.rejected),
                "surplus_count": len(deduped.surplus_pending),
                "duplicate_count": len(deduped.deferred_duplicates),
                "provisional_script": provisional_script,
                "plan": plan_data,
                "plan_sha256": plan_sha256,
                "warnings": warnings,
            }
            return ToolResult(success=True, data=data, artifacts=artifacts)
        except (ValueError, TypeError, KeyError, PydanticValidationError,
                jsonschema.ValidationError, AcousticProfilingError, FileNotFoundError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))
        except Exception as exc:
            return ToolResult(success=False, error=f"clip_selector failed: {exc}")
