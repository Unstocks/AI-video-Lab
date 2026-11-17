"""Typed clip selection dossier contracts; no orchestration behavior."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from lib.models.transcript import FrozenModel, SourceSpan, TimestampProvenance

ValidationState = Literal["VALID", "INVALID_TIMESTAMPS", "INVALID_HOOK_PROVENANCE", "SCHEMA_ERROR"]
EligibilityState = Literal["ELIGIBLE", "REJECTED_COLD_VIEWER", "REJECTED_INCOMPLETE_THOUGHT", "REJECTED_DURATION_OUT_OF_BOUNDS", "REJECTED_MEDIA_QUALITY", "DEFERRED_DUPLICATE"]
ReviewState = Literal["PENDING_REVIEW", "SELECTED_FOR_REVIEW", "AWAITING_HUMAN", "HUMAN_APPROVED", "HUMAN_REJECTED", "HUMAN_REVISED"]
ProductionState = Literal["NOT_STARTED", "PLANNED", "ASSETS_READY", "RENDERED", "QA_PASSED", "QA_FAILED", "EXPORTED"]


class SpokenHookEvidence(FrozenModel):
    text: str
    speaker: Optional[str] = None
    source_spans: tuple[SourceSpan, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def contiguous_single_turn(self):
        if not self.source_spans:
            raise ValueError("spoken_hook requires source spans")
        if self.speaker is not None and not self.speaker.strip():
            raise ValueError("speaker must be non-empty when provided")
        first = self.source_spans[0]
        if any(s.gap_before is not None for s in self.source_spans):
            raise ValueError("spoken_hook spans cannot contain gaps")
        for span in self.source_spans:
            if span.transcript_revision_id != first.transcript_revision_id or span.char_end <= span.char_start:
                raise ValueError("spoken_hook spans must share revision and be non-empty")
        for a, b in zip(self.source_spans, self.source_spans[1:]):
            if (b.segment_id, b.char_start) < (a.segment_id, a.char_start):
                raise ValueError("spoken_hook spans must be ordered")
            if b.segment_id == a.segment_id and a.char_end != b.char_start:
                raise ValueError("same-segment spoken_hook spans must be contiguous")
        return self


class ColdViewerAudit(FrozenModel):
    subject_grounded: bool
    entities_resolved: bool
    pronouns_resolved: bool
    premise_to_payoff_complete: bool
    qualifiers_preserved: bool
    passed: bool
    notes: str = ""
    context_expansion_applied: bool = False

    @model_validator(mode="after")
    def pass_requires_all_checks(self):
        if self.passed and not all((self.subject_grounded, self.entities_resolved, self.pronouns_resolved, self.premise_to_payoff_complete, self.qualifiers_preserved)):
            raise ValueError("passed audit requires all five checks")
        return self


class EditorialCriterionScore(FrozenModel):
    dimension: str
    rationale: str
    score: Optional[float] = None

    @field_validator("score", mode="before")
    @classmethod
    def reject_boolean_score(cls, value):
        if isinstance(value, bool):
            raise ValueError("score must not be boolean")
        return value

    @model_validator(mode="after")
    def rationale_required(self):
        if not self.rationale.strip():
            raise ValueError("rationale must be non-empty")
        return self

    @model_validator(mode="after")
    def score_finite(self):
        if self.score is not None and (isinstance(self.score, bool) or not math.isfinite(self.score)):
            raise ValueError("score must be a finite number")
        return self


class CandidateClip(FrozenModel):
    candidate_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    start_provenance: TimestampProvenance = Field(default_factory=TimestampProvenance)
    end_provenance: TimestampProvenance = Field(default_factory=TimestampProvenance)
    validation_state: ValidationState = "VALID"
    eligibility_state: EligibilityState = "ELIGIBLE"
    review_state: ReviewState = "PENDING_REVIEW"
    production_state: ProductionState = "NOT_STARTED"
    original_spoken_dialogue: str
    spoken_opening: str
    spoken_opening_spans: tuple[SourceSpan, ...] = ()
    spoken_hook: SpokenHookEvidence
    editorial_title: str
    editorial_framing: Optional[str] = None
    cold_viewer_audit: ColdViewerAudit
    editorial_scores: tuple[EditorialCriterionScore, ...] = ()
    human_reviewed_at: Optional[str] = None
    review_metadata: Optional[str] = None
    rejection_reason: Optional[str] = None
    duplicate_of_candidate_id: Optional[str] = None

    @field_validator("start_seconds", "end_seconds", "duration_seconds", mode="before")
    @classmethod
    def reject_boolean_timing(cls, value):
        if isinstance(value, bool):
            raise ValueError("timing values must not be boolean")
        return value

    @model_validator(mode="after")
    def clip_invariants(self):
        if any(isinstance(v, bool) or not math.isfinite(v) for v in (self.start_seconds, self.end_seconds, self.duration_seconds)):
            raise ValueError("clip timestamps and duration must be finite numbers")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        if abs(self.duration_seconds - (self.end_seconds - self.start_seconds)) > 1e-6:
            raise ValueError("duration_seconds must match end_seconds - start_seconds")
        if self.review_state == "HUMAN_APPROVED":
            if not self.human_reviewed_at or not self.review_metadata:
                raise ValueError("HUMAN_APPROVED requires human review metadata")
            if self.validation_state != "VALID" or self.eligibility_state != "ELIGIBLE":
                raise ValueError("HUMAN_APPROVED requires valid and eligible candidate")
        return self


class ClipSelectionPlan(FrozenModel):
    version: Literal["1.0"]
    project_id: str
    source_media_ref: str
    transcript_revision_id: str
    generated_at: str
    candidates: tuple[CandidateClip, ...]

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, value: dict) -> "ClipSelectionPlan":
        return cls.model_validate(value)

    def compute_plan_sha256(self) -> str:
        canonical = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
