"""Temporal/lexical deduplication and portfolio-diversity behavior."""

import pytest

from lib.deduplicator import ClipDeduplicator, lexical_similarity, temporal_iou
from lib.models.clip_plan import CandidateClip, ColdViewerAudit, SpokenHookEvidence
from lib.models.transcript import SourceSpan


def clip(candidate_id, start, end, text, speaker="speaker-a"):
    span = SourceSpan(transcript_revision_id="rev", segment_id=0, char_start=0, char_end=max(1, len(text)))
    return CandidateClip(
        candidate_id=candidate_id, start_seconds=start, end_seconds=end, duration_seconds=end-start,
        original_spoken_dialogue=text, spoken_opening=text, spoken_hook=SpokenHookEvidence(
            text=text, speaker=speaker, source_spans=(span,)),
        editorial_title=candidate_id, cold_viewer_audit=ColdViewerAudit(
            subject_grounded=True, entities_resolved=True, pronouns_resolved=True,
            premise_to_payoff_complete=True, qualifiers_preserved=True, passed=True),
    )


def test_temporal_iou_and_overlapping_candidate_deferred_to_winner():
    assert temporal_iou(0, 100, 40, 140) == pytest.approx(60 / 140)
    assert temporal_iou(0, 10, 20, 30) == 0
    winner, duplicate = clip("winner", 0, 100, "strong insight"), clip("duplicate", 40, 140, "different words")
    result = ClipDeduplicator().deduplicate_and_select([winner, duplicate])
    assert [item.candidate_id for item in result.selected] == ["winner"]
    assert len(result.deferred_duplicates) == 1
    assert result.deferred_duplicates[0].eligibility_state == "DEFERRED_DUPLICATE"
    assert result.deferred_duplicates[0].duplicate_of_candidate_id == "winner"
    assert result.deferred_duplicates[0].rejection_reason.startswith("temporal_overlap(iou=")


def test_lexical_duplicate_works_across_english_hinglish_and_devanagari():
    assert lexical_similarity("कंपनी तेजी से बढ़ी", "कंपनी तेजी से बढ़ी") == 1
    assert lexical_similarity("Yaar, yeh idea kaafi solid hai", "yeh idea kaafi solid hai") > .7
    winner = clip("winner", 0, 10, "हमने ग्राहकों की बात सुनी")
    duplicate = clip("duplicate", 30, 40, "हमने ग्राहकों की बात सुनी")
    result = ClipDeduplicator().deduplicate_and_select([winner, duplicate])
    assert result.deferred_duplicates[0].duplicate_of_candidate_id == "winner"
    assert result.deferred_duplicates[0].rejection_reason.startswith("semantic_duplicate(similarity=")


def test_custom_similarity_seam_is_used_for_non_overlapping_candidates():
    calls = []
    def similarity(left, right):
        calls.append((left.candidate_id, right.candidate_id))
        return .8
    result = ClipDeduplicator(similarity_fn=similarity).deduplicate_and_select([
        clip("one", 0, 10, "first wording"), clip("two", 30, 40, "other wording")])
    assert calls == [("two", "one")]
    assert result.deferred_duplicates[0].duplicate_of_candidate_id == "one"


def test_portfolio_diversity_spreads_speakers_and_time_buckets():
    ranked = [
        clip("top-a", 10, 20, "first moment", "speaker-a"),
        clip("same-bucket-a", 60, 70, "second moment", "speaker-a"),
        clip("far-b", 600, 610, "third moment", "speaker-b"),
    ]
    result = ClipDeduplicator().deduplicate_and_select(ranked, max_clips=2)
    assert [item.candidate_id for item in result.selected] == ["top-a", "far-b"]
    assert all(item.review_state == "SELECTED_FOR_REVIEW" for item in result.selected)
    assert [item.candidate_id for item in result.surplus_pending] == ["same-bucket-a"]
    assert result.surplus_pending[0].review_state == "PENDING_REVIEW"


def test_zero_quota_padding_and_zero_maximum():
    ranked = [clip("one", 0, 10, "first"), clip("two", 30, 40, "second")]
    assert len(ClipDeduplicator().deduplicate_and_select(ranked, max_clips=5).selected) == 2
    assert ClipDeduplicator().deduplicate_and_select([], max_clips=5).selected == ()
    zero = ClipDeduplicator().deduplicate_and_select(ranked, max_clips=0)
    assert zero.selected == () and len(zero.surplus_pending) == 2


def test_character_fourgram_similarity_catches_spelling_and_hinglish_variants():
    score = lexical_similarity("the onboarding setup process", "the on boarding setup process")
    assert score > 0.70


def test_only_gate_passing_candidates_are_accepted_and_invalid_numbers_fail():
    ineligible = clip("bad", 0, 10, "candidate").model_copy(update={"eligibility_state": "REJECTED_COLD_VIEWER"})
    with pytest.raises(ValueError, match="did not pass"):
        ClipDeduplicator().deduplicate_and_select([ineligible])
    with pytest.raises(ValueError):
        temporal_iou(0, float("nan"), 0, 1)
    with pytest.raises(ValueError):
        temporal_iou(True, 2, 0, 1)
