"""Adversarial tests for format ingestion and Unicode source offsets."""

import pytest

from lib.transcript_normalizer import TranscriptNormalizer
from lib.models.transcript import RawTranscriptSegment, RawTranscriptDocument
from lib.models.clip_plan import SpokenHookEvidence


def test_multiformat_provenance_and_word_confidence():
    normalizer = TranscriptNormalizer()
    auto = normalizer.from_youtube_captions({"is_auto_generated":True,"transcript":[{"text":"Hi","start":0,"duration":0}]})
    assert auto.segments[0].timing.timing_source == "auto_caption" and auto.segments[0].end_seconds == 0
    assert auto.segments[0].confidence is None
    creator = normalizer.from_youtube_captions({"is_auto_generated":False,"transcript":[{"text":"Hi","start":0,"duration":1}]})
    assert creator.segments[0].timing.timing_source == "creator_caption"
    whisper = normalizer.from_whisper_transcript({"segments":[{"id":4,"start":0,"end":1,"text":"hi","words":[{"word":"hi","start":0,"end":1,"probability":0.8}]}]})
    assert whisper.segments[0].timing.timing_source == "asr_word" and whisper.segments[0].timing.evidence_quality == "medium_word"
    assert whisper.segments[0].confidence == pytest.approx(0.8)
    no_words = normalizer.from_whisper_transcript({"segments":[{"start":0,"end":1,"text":"hi"}]})
    assert no_words.segments[0].timing.timing_source == "asr_segment" and no_words.segments[0].confidence is None
    srt = normalizer.from_srt_or_vtt("1\n00:00:01,000 --> 00:00:02,500\nHello\n")
    vtt = normalizer.from_srt_or_vtt("WEBVTT\n\n00:01.000 --> 00:02.500\nHello there\n")
    assert srt.segments[0].start_seconds == 1 and srt.segments[0].end_seconds == 2.5
    assert vtt.segments[0].end_seconds == 2.5


@pytest.mark.parametrize("raw,query,expected", [
    ("cafe\u0301 is great", "café", "cafe\u0301"),
    ("\u092f\u0939 \u0915\u093c\u093f\u0924\u093e\u092c \u0905\u091a\u094d\u091b\u0940 \u0939\u0948\u0964", "\u0915\u093c\u093f\u0924\u093e\u092c", "\u0915\u093c\u093f\u0924\u093e\u092c"),
    ("Yaar honestly, yeh architecture bilkul solid hai! Right?", "bilkul solid", "bilkul solid"),
    ("Look at 👨‍👩‍👧‍👦 today!", "today", "today"),
    ("He said:\n  &quot;don&#39;t   stop &amp; ship&quot;", "don't", "don&#39;t"),
    ("He said:\n  &quot;don&#39;t   stop &amp; ship&quot;", "&", "&amp;"),
])
def test_unicode_entity_and_whitespace_mapping_round_trip(raw, query, expected):
    normalizer = TranscriptNormalizer()
    doc = RawTranscriptDocument(segments=(RawTranscriptSegment(segment_id=0, text=raw, start_seconds=0, end_seconds=3),))
    result = normalizer.normalize(doc)
    start = result.normalized_text.index(query)
    spans = result.map_normalized_span_to_raw(start, start + len(query))
    assert len(spans) == 1
    assert result.extract_raw_slices(spans) == [expected]
    assert result.map_raw_span_to_normalized(0, spans[0].char_start, spans[0].char_end) is not None


def test_multisegment_mapping_and_revision_guard():
    normalizer = TranscriptNormalizer()
    doc = RawTranscriptDocument(segments=(
        RawTranscriptSegment(segment_id=0, text="hello", start_seconds=0, end_seconds=1),
        RawTranscriptSegment(segment_id=1, text="world", start_seconds=1, end_seconds=2),
    ))
    result = normalizer.normalize(doc)
    spans = result.map_normalized_span_to_raw(0, len(result.normalized_text))
    assert [s.segment_id for s in spans] == [0, 1]
    assert result.extract_raw_slices(spans) == ["hello", "world"]
    from lib.models.transcript import SourceSpan
    with pytest.raises(ValueError, match="revision"):
        result.extract_raw_slices([SourceSpan(transcript_revision_id="wrong", segment_id=0, char_start=0, char_end=2)])


def test_empty_whitespace_music_overlap_and_sentence_edges():
    normalizer = TranscriptNormalizer()
    empty = normalizer.normalize(RawTranscriptDocument(segments=()))
    assert empty.normalized_text == "" and empty.sentences == ()
    doc = RawTranscriptDocument(segments=(
        RawTranscriptSegment(segment_id=0, text="   ", start_seconds=0, end_seconds=1),
        RawTranscriptSegment(segment_id=1, text="[Music]", start_seconds=0.5, end_seconds=1),
        RawTranscriptSegment(segment_id=2, text="Dr. Smith earned $3.14 in the U.S. today. Next!", start_seconds=2, end_seconds=4),
    ))
    result = normalizer.normalize(doc)
    assert result.non_speech_segment_ids == (1,)
    assert any("overlapping" in w for w in result.warnings)
    assert len(result.sentences) == 3
    assert result.sentences[0].text == "[Music]"
    assert "U.S. today." in result.sentences[1].text


def test_whisper_word_timings_are_stateless_and_explicit():
    normalizer = TranscriptNormalizer()
    whisper = {"segments": [{"id": 0, "start": 0, "end": 1, "text": "hello", "words": [
        {"word": "hello", "start": 0, "end": 0.8, "probability": 0.7},
        {"word": "bad", "start": 0.9, "end": 0.8, "probability": 1.2},
    ]}]}
    first = normalizer.ingest_and_normalize(whisper, "whisper")
    assert first.segments[0].words[0].text == "hello"
    assert len(first.segments[0].words) == 1
    second_doc = RawTranscriptDocument(segments=(RawTranscriptSegment(
        segment_id=0, text="different transcript", start_seconds=0, end_seconds=1),))
    second = normalizer.normalize(second_doc)
    assert second.segments[0].words == ()
    malformed = normalizer.extract_whisper_words({"segments": [{"id": 0, "words": [
        {"word": "bool time", "start": True, "end": 1},
        {"word": "bool confidence", "start": 0, "end": 1, "probability": True},
    ]}]})
    assert len(malformed[0]) == 1
    assert malformed[0][0].text == "bool confidence"
    assert malformed[0][0].confidence is None


def test_whitespace_only_cues_do_not_create_spoken_hook_gaps():
    doc = RawTranscriptDocument(segments=(
        RawTranscriptSegment(segment_id=0, text="Most startups fail", start_seconds=0, end_seconds=1),
        RawTranscriptSegment(segment_id=1, text="   ", start_seconds=1, end_seconds=1.1),
        RawTranscriptSegment(segment_id=2, text="because they skip discovery.", start_seconds=1.1, end_seconds=2),
    ))
    result = TranscriptNormalizer().normalize(doc)
    spans = result.map_normalized_span_to_raw(0, len(result.normalized_text))
    assert [span.segment_id for span in spans] == [0, 2]
    assert all(span.gap_before is None for span in spans)
    SpokenHookEvidence(text=result.normalized_text, source_spans=tuple(spans))


def test_entity_whitespace_and_entity_combining_marks_map_exactly():
    normalizer = TranscriptNormalizer()
    cases = [
        ("hello&nbsp;  world&#10;again", "hello world again", "world", "world"),
        ("cafe&#x301; latte", "caf\u00e9 latte", "caf\u00e9", "cafe&#x301;"),
    ]
    for raw, expected_text, query, expected_raw in cases:
        doc = RawTranscriptDocument(segments=(RawTranscriptSegment(segment_id=0, text=raw, start_seconds=0, end_seconds=1),))
        result = normalizer.normalize(doc)
        assert result.normalized_text == expected_text
        start = result.normalized_text.index(query)
        spans = result.map_normalized_span_to_raw(start, start + len(query))
        assert result.extract_raw_slices(spans) == [expected_raw]


def test_srt_utf8_bom_is_stripped():
    doc = TranscriptNormalizer().from_srt_or_vtt("\ufeff1\n00:00:00,500 --> 00:00:01,500\nHello\n")
    assert len(doc.segments) == 1
    assert doc.segments[0].text == "Hello"
    assert doc.segments[0].start_seconds == pytest.approx(0.5)


def test_non_speech_isolated_and_ellipsis_quotes_do_not_create_fragments():
    doc = RawTranscriptDocument(segments=(
        RawTranscriptSegment(segment_id=0, text="Hello world", start_seconds=0, end_seconds=1),
        RawTranscriptSegment(segment_id=1, text="[Music]", start_seconds=1, end_seconds=2),
        RawTranscriptSegment(segment_id=2, text="Welcome back", start_seconds=2, end_seconds=3),
    ))
    result = TranscriptNormalizer().normalize(doc)
    assert [sentence.text for sentence in result.sentences] == ["Hello world", "[Music]", "Welcome back"]

    quoted = RawTranscriptDocument(segments=(RawTranscriptSegment(
        segment_id=0, text='Wait... really? He said "stop." Then left.', start_seconds=0, end_seconds=4),))
    sentences = TranscriptNormalizer().normalize(quoted).sentences
    assert [sentence.text for sentence in sentences] == ["Wait...", "really?", 'He said "stop."', "Then left."]
