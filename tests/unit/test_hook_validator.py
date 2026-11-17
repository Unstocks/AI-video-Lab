"""Adversarial and multilingual tests for exact spoken-hook provenance."""

import pytest

from lib.hook_validator import validate_hook_provenance
from lib.models.transcript import RawTranscriptDocument, RawTranscriptSegment, SourceSpan
from lib.transcript_normalizer import TranscriptNormalizer


def normalized(*segments):
    doc = RawTranscriptDocument(segments=tuple(RawTranscriptSegment(**segment) for segment in segments))
    return TranscriptNormalizer().normalize(doc)


def test_exact_single_and_multi_segment_hooks_accept_with_un_diarized_speaker():
    single = normalized(dict(segment_id=0, text="The biggest mistake is skipping discovery.", start_seconds=0, end_seconds=5))
    result = validate_hook_provenance("The biggest mistake", single, clip_start_seconds=0, clip_end_seconds=5)
    assert result.valid and result.evidence.speaker is None
    assert single.extract_raw_slices(result.evidence.source_spans) == ["The biggest mistake"]

    multi = normalized(
        dict(segment_id=0, speaker="guest", text="Most startups fail", start_seconds=0, end_seconds=2),
        dict(segment_id=1, speaker="guest", text="   ", start_seconds=2, end_seconds=2.1),
        dict(segment_id=2, speaker="guest", text="because they skip discovery.", start_seconds=2.1, end_seconds=5),
    )
    result = validate_hook_provenance("Most startups fail because they skip discovery", multi,
                                     clip_start_seconds=0, clip_end_seconds=5)
    assert result.valid
    assert [span.segment_id for span in result.evidence.source_spans] == [0, 2]
    assert all(span.gap_before is None for span in result.evidence.source_spans)


@pytest.mark.parametrize("hook,segments,clip_start,clip_end", [
    ("startups fail fast", [dict(segment_id=0, text="startups fail quickly", start_seconds=0, end_seconds=20)], 0, 20),
    ("startups fail because discovery", [dict(segment_id=0, text="startups fail because they skip discovery", start_seconds=0, end_seconds=20)], 0, 20),
    ("cat", [dict(segment_id=0, text="category theory", start_seconds=0, end_seconds=20)], 0, 20),
    ("same phrase", [dict(segment_id=0, text="same phrase here", start_seconds=0, end_seconds=5)], 100, 130),
    ("We [Music] go", [dict(segment_id=0, text="We", start_seconds=0, end_seconds=1),
                        dict(segment_id=1, text="[Music]", start_seconds=1, end_seconds=2),
                        dict(segment_id=2, text="go", start_seconds=2, end_seconds=3)], 0, 3),
])
def test_paraphrase_deletion_substring_time_scope_and_non_speech_rejected(hook, segments, clip_start, clip_end):
    result = validate_hook_provenance(hook, normalized(*segments),
                                     clip_start_seconds=clip_start, clip_end_seconds=clip_end)
    assert not result.valid


def test_cross_speaker_stitch_and_explicit_revision_mismatch_rejected():
    transcript = normalized(
        dict(segment_id=0, speaker="host", text="We need to rethink", start_seconds=0, end_seconds=2),
        dict(segment_id=1, speaker="guest", text="the entire market.", start_seconds=2, end_seconds=4),
    )
    result = validate_hook_provenance("We need to rethink the entire market", transcript,
                                     clip_start_seconds=0, clip_end_seconds=4)
    assert not result.valid and "multiple speakers" in result.failure_reason
    bad_span = SourceSpan(transcript_revision_id="wrong", segment_id=0, char_start=0, char_end=4)
    assert not validate_hook_provenance("We", transcript, source_spans=[bad_span]).valid


def test_opening_window_can_warn_or_fail():
    transcript = normalized(
        dict(segment_id=0, text="A long introduction ends.", start_seconds=0, end_seconds=10),
        dict(segment_id=1, text="The actual hook lands here.", start_seconds=10, end_seconds=30),
    )
    warned = validate_hook_provenance("The actual hook lands here", transcript,
                                     clip_start_seconds=0, clip_end_seconds=30,
                                     opening_window_seconds=5)
    assert warned.valid and warned.warnings
    rejected = validate_hook_provenance("The actual hook lands here", transcript,
                                       clip_start_seconds=0, clip_end_seconds=30,
                                       opening_window_seconds=5, require_in_opening_window=True)
    assert not rejected.valid and "opening window" in rejected.failure_reason


@pytest.mark.parametrize("raw,hook", [
    ("यह क़िताब सच में कमाल की है", "यह क़िताब सच में कमाल की है"),
    ("yeh idea kaafi solid hai", "yeh idea kaafi solid hai"),
    ("cafe\u0301 is open", "caf\u00e9 is open"),
    ("We don&#39;t quit &amp; ship", "We don't quit & ship"),
])
def test_unicode_hooks_recover_exact_original_raw_slice(raw, hook):
    transcript = normalized(dict(segment_id=0, speaker=None, text=raw, start_seconds=0, end_seconds=10))
    result = validate_hook_provenance(hook, transcript, clip_start_seconds=0, clip_end_seconds=10)
    assert result.valid
    recovered = " ".join(transcript.extract_raw_slices(result.evidence.source_spans))
    assert recovered == raw


def test_explicit_source_spans_reject_non_contiguous_and_expected_speaker_mismatch():
    transcript = normalized(
        dict(segment_id=0, speaker="guest", text="The first half", start_seconds=0, end_seconds=1),
        dict(segment_id=1, speaker="guest", text="omitted words", start_seconds=1, end_seconds=2),
        dict(segment_id=2, speaker="guest", text="the final half", start_seconds=2, end_seconds=3),
    )
    doc = transcript.raw_document
    spans = [SourceSpan(transcript_revision_id=doc.transcript_revision_id, segment_id=0, char_start=0, char_end=14),
             SourceSpan(transcript_revision_id=doc.transcript_revision_id, segment_id=2, char_start=0, char_end=14)]
    result = validate_hook_provenance("The first half the final half", transcript, source_spans=spans)
    assert not result.valid and "skips" in result.failure_reason
    assert not validate_hook_provenance("The first half", transcript, clip_start_seconds=0, clip_end_seconds=3,
                                        expected_speaker="host").valid


def test_adjacent_explicit_spans_within_one_segment_do_not_gain_artificial_space():
    transcript = normalized(dict(segment_id=0, speaker="guest", text="hello world", start_seconds=0, end_seconds=1))
    revision = transcript.raw_document.transcript_revision_id
    spans = (SourceSpan(transcript_revision_id=revision, segment_id=0, char_start=0, char_end=5),
             SourceSpan(transcript_revision_id=revision, segment_id=0, char_start=5, char_end=11))
    result = validate_hook_provenance("hello world", transcript, source_spans=spans)
    assert result.valid


def test_case_insensitive_verbatim_hook_preserves_original_source_coordinates():
    transcript = normalized(dict(segment_id=0, text="the biggest mistake founders make", start_seconds=0, end_seconds=5))
    result = validate_hook_provenance("The Biggest Mistake Founders Make", transcript,
                                     clip_start_seconds=0, clip_end_seconds=5)
    assert result.valid
    assert transcript.extract_raw_slices(result.evidence.source_spans) == ["the biggest mistake founders make"]
    assert result.matched_norm_span == (0, len("the biggest mistake founders make"))
