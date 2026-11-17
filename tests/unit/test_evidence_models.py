"""Evidence model semantic invariants and Unicode serialization fidelity."""

import json

import pytest
from pydantic import ValidationError

from lib.models import (
    CandidateClip, ClipSelectionPlan, ColdViewerAudit, EditorialCriterionScore, RawTranscriptDocument,
    RawTranscriptSegment, SourceSpan, SpokenHookEvidence, TimestampProvenance,
)


def span(start=0, end=5, **kwargs):
    return SourceSpan(transcript_revision_id="rev", segment_id=0, char_start=start, char_end=end, **kwargs)


def valid_plan_payload():
    candidate = CandidateClip(
        candidate_id="c1", start_seconds=0, end_seconds=10, duration_seconds=10,
        original_spoken_dialogue="Hello world", spoken_opening="Hello", spoken_opening_spans=(span(),),
        spoken_hook=SpokenHookEvidence(text="Hello", speaker="speaker-1", source_spans=(span(),)),
        editorial_title="A title", cold_viewer_audit=ColdViewerAudit(
            subject_grounded=True, entities_resolved=True, pronouns_resolved=True,
            premise_to_payoff_complete=True, qualifiers_preserved=True, passed=True,
        ),
    )
    return ClipSelectionPlan(version="1.0", project_id="p1", source_media_ref="source.mp4", transcript_revision_id="rev", generated_at="2026-11-17T00:00:00Z", candidates=(candidate,)).to_dict()


def test_orthogonal_timing_and_confidence_defaults_none():
    p = TimestampProvenance(timing_source="asr_word", alignment_method="forced_alignment_ctc", evidence_quality="medium_word", transformation="raw_unmodified")
    assert p.confidence is None and p.uncertainty_seconds is None
    with pytest.raises(ValidationError):
        TimestampProvenance(uncertainty_seconds=-0.1)
    with pytest.raises(ValidationError):
        TimestampProvenance(confidence=1.1)


@pytest.mark.parametrize("kwargs", [{"char_start":-1,"char_end":1}, {"char_start":2,"char_end":1}])
def test_source_span_rejects_negative_or_inverted_offsets(kwargs):
    with pytest.raises(ValidationError):
        SourceSpan(transcript_revision_id="rev", segment_id=0, **kwargs)


def test_inverted_timestamps_approval_without_review_and_hook_gaps_rejected():
    with pytest.raises(ValidationError):
        RawTranscriptSegment(segment_id=0, text="x", start_seconds=2, end_seconds=1)
    base = valid_plan_payload()["candidates"][0]
    base.update(review_state="HUMAN_APPROVED")
    with pytest.raises(ValidationError):
        CandidateClip.model_validate(base)
    with pytest.raises(ValidationError):
        SpokenHookEvidence(text="ab", speaker="s", source_spans=(span(0,1), span(1,2,gap_before=" ")))


def test_hook_may_cross_ordered_caption_segments():
    evidence = SpokenHookEvidence(text="hello world", source_spans=(span(0, 5), SourceSpan(transcript_revision_id="rev", segment_id=1, char_start=0, char_end=5)))
    assert len(evidence.source_spans) == 2


def test_revision_hash_is_identical_for_dict_and_model_inputs():
    raw = {"segment_id": 0, "text": "hello", "start_seconds": 0.0, "end_seconds": 1.0}
    from_dict = RawTranscriptDocument(segments=[raw])
    from_model = RawTranscriptDocument(segments=[RawTranscriptSegment(**raw)])
    assert from_dict.transcript_revision_id == from_model.transcript_revision_id


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_and_negative_timing_values_are_rejected(value):
    with pytest.raises(ValidationError):
        RawTranscriptSegment(segment_id=0, text="x", start_seconds=value, end_seconds=1)
    with pytest.raises(ValidationError):
        TimestampProvenance(confidence=value)
    with pytest.raises(ValidationError):
        CandidateClip.model_validate({**valid_plan_payload()["candidates"][0], "start_seconds": value})
    with pytest.raises(ValidationError):
        EditorialCriterionScore(dimension="x", rationale="because", score=value)
    with pytest.raises(ValidationError):
        RawTranscriptSegment(segment_id=0, text="x", start_seconds=-1, end_seconds=1)


@pytest.mark.parametrize("text", ["Hello", "नमस्ते", "Namaste भाई", "e\u0301", "👩‍👩‍👧‍👦✨"])
def test_revision_and_plan_hash_determinism_and_unicode_round_trip(text):
    segment = RawTranscriptSegment(segment_id=0, speaker="speaker", text=text, start_seconds=0, end_seconds=1)
    doc = RawTranscriptDocument(segments=(segment,))
    doc2 = RawTranscriptDocument(segments=(segment,))
    assert doc.transcript_revision_id == doc2.transcript_revision_id
    plan = ClipSelectionPlan.from_dict(valid_plan_payload())
    encoded = json.dumps(plan.to_dict(), ensure_ascii=False)
    restored = ClipSelectionPlan.from_dict(json.loads(encoded))
    assert restored.to_dict() == plan.to_dict()
    assert restored.compute_plan_sha256() == plan.compute_plan_sha256()
    round_trip = RawTranscriptDocument.model_validate_json(doc.model_dump_json())
    assert round_trip.segments[0].text == text
