"""Immutable transcript and timestamp evidence domain models (Layer 0)."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TimingSource = Literal["creator_caption", "auto_caption", "asr_segment", "asr_word", "vad_region", "unknown"]
AlignmentMethod = Literal["none", "caption_container", "asr_cross_attention", "forced_alignment_ctc", "vad_energy_or_neural", "character_interpolation", "human_manual"]
EvidenceQuality = Literal["high_subframe", "medium_word", "coarse_segment", "low_estimated", "unknown"]
BoundaryTransformation = Literal["raw_unmodified", "silence_proximity_adjusted", "vad_onset_offset_adjusted", "editorial_context_expanded", "human_adjusted"]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TimestampProvenance(FrozenModel):
    timing_source: TimingSource = "unknown"
    alignment_method: AlignmentMethod = "none"
    evidence_quality: EvidenceQuality = "unknown"
    transformation: BoundaryTransformation = "raw_unmodified"
    uncertainty_seconds: Optional[float] = Field(default=None, ge=0)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    human_reviewed: bool = False
    original_seconds: Optional[float] = Field(default=None, ge=0)

    @field_validator("uncertainty_seconds", "confidence", "original_seconds", mode="before")
    @classmethod
    def reject_boolean_numeric_values(cls, value):
        if isinstance(value, bool):
            raise ValueError("boolean values are not numeric evidence")
        return value

    @field_validator("uncertainty_seconds", "confidence", "original_seconds")
    @classmethod
    def finite_optional_values(cls, value):
        if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
            raise ValueError("numeric evidence values must be finite numbers")
        return value

    @field_validator("uncertainty_seconds")
    @classmethod
    def nonnegative_uncertainty(cls, value):
        if value is not None and value < 0:
            raise ValueError("uncertainty_seconds must be nonnegative")
        return value

    @field_validator("original_seconds")
    @classmethod
    def nonnegative_original_time(cls, value):
        if value is not None and value < 0:
            raise ValueError("original_seconds must be nonnegative")
        return value

    @field_validator("confidence")
    @classmethod
    def bounded_confidence(cls, value):
        if value is not None and (isinstance(value, bool) or not 0 <= value <= 1):
            raise ValueError("confidence must be between 0 and 1")
        return value


class SourceSpan(FrozenModel):
    transcript_revision_id: str
    segment_id: int = Field(ge=0)
    coordinate_system: Literal["unicode_codepoint_half_open"] = "unicode_codepoint_half_open"
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    gap_before: Optional[str] = None

    @field_validator("segment_id", "char_start", "char_end", mode="before")
    @classmethod
    def reject_boolean_offsets(cls, value):
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid offsets")
        return value

    @field_validator("transcript_revision_id")
    @classmethod
    def revision_required(cls, value):
        if not value.strip():
            raise ValueError("transcript_revision_id must be non-empty")
        return value

    @model_validator(mode="after")
    def ordered_span(self):
        if isinstance(self.segment_id, bool) or isinstance(self.char_start, bool) or isinstance(self.char_end, bool):
            raise ValueError("span offsets and segment_id must be integers, not bool")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise ValueError("SourceSpan requires 0 <= char_start <= char_end")
        return self


class RawTranscriptSegment(FrozenModel):
    segment_id: int
    speaker: Optional[str] = None
    text: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    timing: TimestampProvenance = Field(default_factory=TimestampProvenance)
    confidence: Optional[float] = None

    @field_validator("segment_id", mode="before")
    @classmethod
    def reject_boolean_id(cls, value):
        if isinstance(value, bool):
            raise ValueError("segment_id must be an integer, not bool")
        return value

    @field_validator("start_seconds", "end_seconds", "confidence", mode="before")
    @classmethod
    def reject_boolean_numbers(cls, value):
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid numeric values")
        return value

    @model_validator(mode="after")
    def valid_interval(self):
        if any(isinstance(v, bool) or not math.isfinite(v) for v in (self.start_seconds, self.end_seconds)):
            raise ValueError("timestamps must be finite numbers")
        if isinstance(self.segment_id, bool):
            raise ValueError("segment_id must be an integer, not bool")
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be >= start_seconds")
        return self

    @field_validator("confidence")
    @classmethod
    def bounded_confidence(cls, value):
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class RawTranscriptDocument(FrozenModel):
    transcript_revision_id: Optional[str] = None
    segments: tuple[RawTranscriptSegment, ...]

    @staticmethod
    def compute_revision_id(segments) -> str:
        payload = [s.model_dump(mode="json") if isinstance(s, RawTranscriptSegment) else s for s in segments]
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def assign_revision(self):
        if not self.transcript_revision_id:
            object.__setattr__(self, "transcript_revision_id", self.compute_revision_id(self.segments))
        return self
