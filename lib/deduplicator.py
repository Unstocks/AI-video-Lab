"""Deterministic temporal/lexical deduplication and portfolio diversity."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from lib.models.clip_plan import CandidateClip


@dataclass(frozen=True)
class DeduplicationResult:
    selected: tuple[CandidateClip, ...]
    deferred_duplicates: tuple[CandidateClip, ...]
    surplus_pending: tuple[CandidateClip, ...]


def _finite_time(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def temporal_iou(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    a0 = _finite_time(start_a, "start_a")
    a1 = _finite_time(end_a, "end_a")
    b0 = _finite_time(start_b, "start_b")
    b1 = _finite_time(end_b, "end_b")
    if a1 <= a0 or b1 <= b0:
        raise ValueError("each interval must have positive duration")
    intersection = max(0.0, min(a1, b1) - max(a0, b0))
    union = (a1 - a0) + (b1 - b0) - intersection
    return intersection / union if union > 0 else 0.0


_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)


def lexical_similarity(text_a: str, text_b: str) -> float:
    tokens_a = set(_TOKENS.findall(text_a.casefold()))
    tokens_b = set(_TOKENS.findall(text_b.casefold()))
    if not tokens_a and not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    token_score = len(tokens_a & tokens_b) / len(union) if union else 0.0
    # Compact whitespace for character shingles so spelling variants that
    # insert/remove a token boundary ("onboarding" / "on boarding") retain
    # their shared character evidence. Word-token Jaccard above still captures
    # the lexical boundary difference independently.
    normalized_a = "".join(_TOKENS.findall(text_a.casefold()))
    normalized_b = "".join(_TOKENS.findall(text_b.casefold()))
    grams_a = {normalized_a[index:index + 4] for index in range(max(0, len(normalized_a) - 3))}
    grams_b = {normalized_b[index:index + 4] for index in range(max(0, len(normalized_b) - 3))}
    char_union = grams_a | grams_b
    char_score = len(grams_a & grams_b) / len(char_union) if char_union else 0.0
    return max(token_score, 0.85 * char_score)


class ClipDeduplicator:
    def __init__(self, *, temporal_iou_threshold: float = 0.35,
                 semantic_similarity_threshold: float = 0.70,
                 similarity_fn: Optional[Callable[[CandidateClip, CandidateClip], float]] = None,
                 diversity_time_bucket_seconds: float = 300.0) -> None:
        self.temporal_iou_threshold = self._threshold(temporal_iou_threshold, "temporal_iou_threshold")
        self.semantic_similarity_threshold = self._threshold(semantic_similarity_threshold,
                                                              "semantic_similarity_threshold")
        self.diversity_time_bucket_seconds = _finite_time(diversity_time_bucket_seconds,
                                                          "diversity_time_bucket_seconds")
        if self.diversity_time_bucket_seconds <= 0:
            raise ValueError("diversity_time_bucket_seconds must be greater than zero")
        self.similarity_fn = similarity_fn

    @staticmethod
    def _threshold(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"{name} must be a finite value between 0 and 1")
        return float(value)

    def deduplicate_and_select(self, ranked_eligible: Sequence[CandidateClip], *,
                               max_clips: Optional[int] = None) -> DeduplicationResult:
        if max_clips is not None and (isinstance(max_clips, bool) or not isinstance(max_clips, int) or max_clips < 0):
            raise ValueError("max_clips must be a nonnegative integer or None")
        ids = [clip.candidate_id for clip in ranked_eligible]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique")
        winners: list[CandidateClip] = []
        deferred: list[CandidateClip] = []
        for clip in ranked_eligible:
            if clip.validation_state != "VALID" or clip.eligibility_state != "ELIGIBLE":
                raise ValueError(f"candidate {clip.candidate_id} did not pass validation and eligibility gates")
            duplicate_of = None
            reason = None
            for winner in winners:
                overlap = temporal_iou(clip.start_seconds, clip.end_seconds,
                                       winner.start_seconds, winner.end_seconds)
                if overlap >= self.temporal_iou_threshold:
                    duplicate_of = winner.candidate_id
                    reason = f"temporal_overlap(iou={overlap:.2f}) with {winner.candidate_id}"
                    break
                similarity = (self.similarity_fn(clip, winner) if self.similarity_fn is not None else
                              lexical_similarity(clip.original_spoken_dialogue, winner.original_spoken_dialogue))
                if isinstance(similarity, bool) or not isinstance(similarity, (int, float)) or not math.isfinite(similarity) or not 0 <= similarity <= 1:
                    raise ValueError("similarity_fn must return a finite value between 0 and 1")
                if similarity >= self.semantic_similarity_threshold:
                    duplicate_of = winner.candidate_id
                    reason = f"semantic_duplicate(similarity={similarity:.2f}) with {winner.candidate_id}"
                    break
            if duplicate_of is None:
                winners.append(clip)
            else:
                deferred.append(clip.model_copy(update={
                    "eligibility_state": "DEFERRED_DUPLICATE",
                    "duplicate_of_candidate_id": duplicate_of,
                    "rejection_reason": reason,
                }))

        if max_clips is None or len(winners) <= max_clips:
            return DeduplicationResult(
                tuple(clip.model_copy(update={"review_state": "SELECTED_FOR_REVIEW"}) for clip in winners),
                tuple(deferred), (),
            )
        if max_clips == 0:
            return DeduplicationResult((), tuple(deferred),
                                      tuple(clip.model_copy(update={"review_state": "PENDING_REVIEW"}) for clip in winners))

        selected = [winners[0]]
        remaining = winners[1:]
        while remaining and len(selected) < max_clips:
            speakers = {clip.spoken_hook.speaker for clip in selected}
            buckets = {int(clip.start_seconds // self.diversity_time_bucket_seconds) for clip in selected}
            def diversity_priority(clip: CandidateClip) -> int:
                return int(clip.spoken_hook.speaker not in speakers) + int(
                    int(clip.start_seconds // self.diversity_time_bucket_seconds) not in buckets)
            best_index = max(range(len(remaining)), key=lambda i: (diversity_priority(remaining[i]), -i))
            selected.append(remaining.pop(best_index))
        selected_ids = {clip.candidate_id for clip in selected}
        surplus = [clip for clip in winners if clip.candidate_id not in selected_ids]
        return DeduplicationResult(
            tuple(clip.model_copy(update={"review_state": "SELECTED_FOR_REVIEW"}) for clip in selected),
            tuple(deferred),
            tuple(clip.model_copy(update={"review_state": "PENDING_REVIEW"}) for clip in surplus),
        )
