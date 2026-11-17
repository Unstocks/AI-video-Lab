"""Hard editorial eligibility gates and explainable candidate ordering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, TYPE_CHECKING

from lib.cold_viewer_auditor import ColdViewerAuditResult, ColdViewerAuditor
from lib.hook_validator import HookValidationResult, validate_hook_provenance
from lib.models.clip_plan import CandidateClip, ColdViewerAudit, EditorialCriterionScore, SpokenHookEvidence
from lib.models.transcript import SourceSpan, TimestampProvenance
from lib.transcript_normalizer import NormalizedTranscriptResult

if TYPE_CHECKING:
    from lib.acoustic_profiler import AcousticProfile, AcousticProfiler, BoundaryRefinementResult
    from lib.conversation_structure import ConversationTopology


@dataclass(frozen=True)
class CandidateProposal:
    candidate_id: str
    start_seconds: float
    end_seconds: float
    original_spoken_dialogue: str
    spoken_opening: str
    spoken_hook_text: str
    editorial_title: str
    cold_viewer_audit: ColdViewerAudit
    spoken_opening_spans: tuple[SourceSpan, ...] = ()
    spoken_hook_spans: Optional[tuple[SourceSpan, ...]] = None
    expected_speaker: Optional[str] = None
    editorial_framing: Optional[str] = None
    editorial_scores: tuple[EditorialCriterionScore, ...] = ()
    start_provenance: Optional[TimestampProvenance] = None
    end_provenance: Optional[TimestampProvenance] = None
    thought_complete_start: bool = True
    thought_complete_end: bool = True
    media_usable: bool = True
    archetype: Optional[str] = None


@dataclass(frozen=True)
class EvaluatedCandidate:
    clip: CandidateClip
    rank_score: Optional[float]
    hook_result: HookValidationResult
    cold_viewer_result: ColdViewerAuditResult
    boundary_refinement: Optional["BoundaryRefinementResult"] = None
    archetype: Optional[str] = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationBatchResult:
    eligible_ranked: tuple[EvaluatedCandidate, ...]
    rejected: tuple[EvaluatedCandidate, ...]
    warnings: tuple[str, ...] = ()


class EditorialEvaluator:
    def __init__(self, *, min_duration_seconds: float = 15.0, max_duration_seconds: float = 120.0,
                 preferred_max_duration_seconds: float = 90.0, min_audible_lufs: float = -55.0,
                 opening_window_seconds: float = 5.0, require_hook_in_opening_window: bool = False,
                 cold_viewer_auditor: Optional[ColdViewerAuditor] = None,
                 acoustic_profiler: Optional["AcousticProfiler"] = None) -> None:
        self.min_duration_seconds = self._finite(min_duration_seconds, "min_duration_seconds", minimum=0)
        self.max_duration_seconds = self._finite(max_duration_seconds, "max_duration_seconds", minimum=0)
        self.preferred_max_duration_seconds = self._finite(preferred_max_duration_seconds,
                                                           "preferred_max_duration_seconds", minimum=0)
        self.min_audible_lufs = self._finite(min_audible_lufs, "min_audible_lufs")
        self.opening_window_seconds = self._finite(opening_window_seconds, "opening_window_seconds", minimum=0)
        if self.min_duration_seconds >= self.max_duration_seconds:
            raise ValueError("min_duration_seconds must be less than max_duration_seconds")
        if self.preferred_max_duration_seconds > self.max_duration_seconds:
            raise ValueError("preferred_max_duration_seconds must not exceed max_duration_seconds")
        self.require_hook_in_opening_window = require_hook_in_opening_window
        self.cold_viewer_auditor = cold_viewer_auditor or ColdViewerAuditor(max_duration_seconds=self.max_duration_seconds)
        self.acoustic_profiler = acoustic_profiler

    @staticmethod
    def _finite(value: float, name: str, *, minimum: Optional[float] = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        result = float(value)
        if minimum is not None and result < minimum:
            raise ValueError(f"{name} must be >= {minimum}")
        return result

    @staticmethod
    def _timestamps_valid(proposal: CandidateProposal) -> bool:
        return (not isinstance(proposal.start_seconds, bool) and not isinstance(proposal.end_seconds, bool)
                and math.isfinite(proposal.start_seconds) and math.isfinite(proposal.end_seconds)
                and proposal.start_seconds >= 0 and proposal.end_seconds > proposal.start_seconds)

    @staticmethod
    def _fallback_evidence(proposal: CandidateProposal, normalized: NormalizedTranscriptResult) -> Optional[SpokenHookEvidence]:
        if proposal.spoken_hook_spans:
            try:
                return SpokenHookEvidence(text=proposal.spoken_hook_text.strip(),
                                          speaker=proposal.expected_speaker,
                                          source_spans=proposal.spoken_hook_spans)
            except Exception:
                pass
        segment = next((s for s in normalized.raw_document.segments if s.text.strip()), None)
        if segment is None:
            return None
        anchor = SourceSpan(transcript_revision_id=normalized.raw_document.transcript_revision_id or "",
                            segment_id=segment.segment_id, char_start=0, char_end=min(1, len(segment.text)))
        return SpokenHookEvidence(text=proposal.spoken_hook_text.strip(), speaker=segment.speaker,
                                  source_spans=(anchor,))

    @staticmethod
    def _quality_rank(clip: CandidateClip, normalized: NormalizedTranscriptResult) -> int:
        by_id = {s.segment_id: s for s in normalized.raw_document.segments}
        ranks = {"high_subframe": 0, "medium_word": 1, "coarse_segment": 2, "low_estimated": 3, "unknown": 4}
        quality = [ranks[by_id[s.segment_id].timing.evidence_quality]
                   for s in clip.spoken_hook.source_spans if s.segment_id in by_id]
        return max(quality, default=4)

    def evaluate_candidates(self, proposals: Sequence[CandidateProposal], normalized: NormalizedTranscriptResult,
                            *, topology: Optional["ConversationTopology"] = None,
                            acoustic_profile: Optional["AcousticProfile"] = None) -> EvaluationBatchResult:
        ids = [proposal.candidate_id for proposal in proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique within a batch")
        eligible: list[EvaluatedCandidate] = []
        rejected: list[EvaluatedCandidate] = []
        batch_warnings: list[str] = []

        for proposal in proposals:
            if not self._timestamps_valid(proposal):
                batch_warnings.append(f"{proposal.candidate_id}: rejected diagnostic only; invalid timestamps cannot be represented by CandidateClip")
                continue

            start, end = float(proposal.start_seconds), float(proposal.end_seconds)
            start_provenance = proposal.start_provenance or TimestampProvenance()
            end_provenance = proposal.end_provenance or TimestampProvenance()
            boundary = None
            candidate_warnings: list[str] = []
            if acoustic_profile is not None:
                try:
                    from lib.acoustic_profiler import AcousticProfiler
                    profiler = self.acoustic_profiler or AcousticProfiler()
                    boundary = profiler.suggest_boundary_refinement(
                        start, end, acoustic_profile,
                        thought_complete_start=proposal.thought_complete_start,
                        thought_complete_end=proposal.thought_complete_end,
                        start_provenance=proposal.start_provenance,
                        end_provenance=proposal.end_provenance,
                    )
                    start, end = boundary.refined_start_seconds, boundary.refined_end_seconds
                    start_provenance, end_provenance = boundary.start_provenance, boundary.end_provenance
                    candidate_warnings.extend(boundary.warnings)
                except (ValueError, TypeError) as exc:
                    candidate_warnings.append(f"acoustic boundary refinement unavailable: {exc}")

            hook_result = validate_hook_provenance(
                proposal.spoken_hook_text, normalized,
                clip_start_seconds=start, clip_end_seconds=end,
                source_spans=proposal.spoken_hook_spans or None,
                expected_speaker=proposal.expected_speaker,
                opening_window_seconds=self.opening_window_seconds,
                require_in_opening_window=self.require_hook_in_opening_window,
            )
            cold_result = self.cold_viewer_auditor.audit(
                spoken_opening=proposal.spoken_opening,
                original_spoken_dialogue=proposal.original_spoken_dialogue,
                start_seconds=start, end_seconds=end,
                proposed_audit=proposal.cold_viewer_audit,
                editorial_framing=proposal.editorial_framing,
                topology=topology,
            )
            candidate_warnings.extend(hook_result.warnings)
            candidate_warnings.extend(cold_result.warnings)
            evidence = hook_result.evidence or self._fallback_evidence(proposal, normalized)
            if evidence is None:
                batch_warnings.append(f"{proposal.candidate_id}: no non-empty transcript segment exists for rejected-hook provenance anchor")
                continue

            duration = end - start
            state = "VALID"
            eligibility = "ELIGIBLE"
            rejection_reason = None
            if not hook_result.valid:
                state = "INVALID_HOOK_PROVENANCE"
                rejection_reason = f"hook_validation_failed: {hook_result.failure_reason}"
            elif duration < self.min_duration_seconds or duration > self.max_duration_seconds:
                eligibility = "REJECTED_DURATION_OUT_OF_BOUNDS"
                rejection_reason = f"duration {duration:.3f}s outside [{self.min_duration_seconds}, {self.max_duration_seconds}] seconds"
            elif not proposal.thought_complete_start or not proposal.thought_complete_end:
                eligibility = "REJECTED_INCOMPLETE_THOUGHT"
                rejection_reason = "clip start or end is not marked thought-complete"
            elif not cold_result.passed or cold_result.inherently_episodic:
                eligibility = "REJECTED_COLD_VIEWER"
                rejection_reason = "; ".join(cold_result.failure_reasons) or (
                    "required context exceeds the hard duration ceiling" if cold_result.inherently_episodic
                    else "cold-viewer audit failed")
            elif not proposal.media_usable:
                eligibility = "REJECTED_MEDIA_QUALITY"
                rejection_reason = "media marked unusable"
            elif acoustic_profile is not None and acoustic_profile.energy_profile:
                loudness = acoustic_profile.average_loudness_lufs(start, end)
                if loudness is None or loudness < self.min_audible_lufs:
                    eligibility = "REJECTED_MEDIA_QUALITY"
                    rejection_reason = "audio loudness is unavailable or below the configured minimum"

            if duration > self.preferred_max_duration_seconds and duration <= self.max_duration_seconds:
                candidate_warnings.append("candidate exceeds preferred duration but remains within the hard maximum")
            scores = tuple(proposal.editorial_scores)
            numeric_scores = [float(score.score) for score in scores if score.score is not None]
            rank_score = sum(numeric_scores) / len(numeric_scores) if numeric_scores else None
            clip = CandidateClip(
                candidate_id=proposal.candidate_id, start_seconds=start, end_seconds=end, duration_seconds=duration,
                start_provenance=start_provenance, end_provenance=end_provenance,
                validation_state=state, eligibility_state=eligibility, review_state="PENDING_REVIEW",
                production_state="NOT_STARTED", original_spoken_dialogue=proposal.original_spoken_dialogue,
                spoken_opening=proposal.spoken_opening, spoken_opening_spans=proposal.spoken_opening_spans,
                spoken_hook=evidence, editorial_title=proposal.editorial_title,
                editorial_framing=proposal.editorial_framing, cold_viewer_audit=cold_result.audit,
                editorial_scores=scores, rejection_reason=rejection_reason,
            )
            evaluated = EvaluatedCandidate(clip, rank_score, hook_result, cold_result, boundary,
                                           proposal.archetype, tuple(candidate_warnings))
            if state == "VALID" and eligibility == "ELIGIBLE":
                eligible.append(evaluated)
            else:
                rejected.append(evaluated)

        eligible.sort(key=lambda item: (
            item.rank_score is None,
            -(item.rank_score or 0.0),
            -len(item.clip.editorial_scores),
            self._quality_rank(item.clip, normalized),
            item.clip.start_seconds,
            item.clip.candidate_id,
        ))
        return EvaluationBatchResult(tuple(eligible), tuple(rejected), tuple(batch_warnings))
