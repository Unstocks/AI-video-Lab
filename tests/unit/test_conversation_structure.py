"""Tests for deterministic turn, Q&A, and context topology."""

from lib.transcript_normalizer import TranscriptNormalizer
from lib.conversation_structure import ConversationStructureAnalyzer
from lib.models.transcript import RawTranscriptDocument, RawTranscriptSegment


def topology(segments, **kwargs):
    doc = RawTranscriptDocument(segments=tuple(RawTranscriptSegment(**s) for s in segments))
    return ConversationStructureAnalyzer(**kwargs).analyze(TranscriptNormalizer().normalize(doc))


def test_turns_merge_same_speaker_and_split_on_speaker_change():
    t = topology([
        dict(segment_id=0,speaker="host",text="First thought.",start_seconds=0,end_seconds=1),
        dict(segment_id=1,speaker="host",text="Second thought.",start_seconds=1,end_seconds=2),
        dict(segment_id=2,speaker="guest",text="An answer.",start_seconds=2,end_seconds=3),
    ])
    assert len(t.turns) == 2 and t.turns[0].sentence_ids == (0,1)


def test_question_answer_detection_and_lookback():
    t = topology([
        dict(segment_id=0,speaker="host",text="Why did it fail?",start_seconds=0,end_seconds=2),
        dict(segment_id=1,speaker="guest",text="It failed because of scale.",start_seconds=2,end_seconds=4),
        dict(segment_id=2,speaker="host",text="kya yeh scale karega",start_seconds=5,end_seconds=6),
        dict(segment_id=3,speaker="guest",text="Yes, it will scale.",start_seconds=6,end_seconds=7),
        dict(segment_id=4,speaker="host",text="why does this matter",start_seconds=100,end_seconds=102),
        dict(segment_id=5,speaker="guest",text="It matters a lot.",start_seconds=102,end_seconds=104),
        dict(segment_id=6,speaker="guest",text="Later response.",start_seconds=200,end_seconds=201),
    ])
    assert len(t.qa_pairs) == 3
    assert t.find_preceding_question(1).text == "Why did it fail?"
    assert t.find_preceding_question(6, max_lookback_seconds=45) is None


def test_context_window_expands_to_full_turns_and_blocks():
    t = topology([
        dict(segment_id=0,speaker="a",text="Start here.",start_seconds=0,end_seconds=2),
        dict(segment_id=1,speaker="b",text="Full next sentence.",start_seconds=2,end_seconds=4),
        dict(segment_id=2,speaker="a",text="Far away.",start_seconds=20,end_seconds=21),
    ])
    context = t.get_context_window(2.5, 2.6, before_seconds=0, after_seconds=0)
    assert [turn.text for turn in context] == ["Full next sentence."]
    assert t.get_containing_block(2.5, 2.6) is not None


def test_empty_and_undiarized_pause_split():
    empty = topology([])
    assert empty.turns == () and empty.blocks == () and empty.total_duration_seconds == 0
    t = topology([
        dict(segment_id=0,text="First monologue part.",start_seconds=0,end_seconds=2),
        dict(segment_id=1,text="Second monologue part.",start_seconds=10,end_seconds=12),
    ])
    assert len(t.turns) == 2 and not t.has_speaker_diarization


def test_multisentence_and_devanagari_questions_pair_with_answers():
    t = topology([
        dict(segment_id=0, speaker="host", text="You scaled to 10M users in two years. How did you actually do that", start_seconds=0, end_seconds=3),
        dict(segment_id=1, speaker="guest", text="We focused on one thing.", start_seconds=3, end_seconds=4),
        dict(segment_id=2, speaker="host", text="क्या यह मॉडल सच में काम करता है", start_seconds=5, end_seconds=7),
        dict(segment_id=3, speaker="guest", text="हाँ, यह काम करता है।", start_seconds=7, end_seconds=8),
    ])
    assert t.turns[0].is_question
    assert t.turns[2].is_question
    assert [(pair.question_turn_id, pair.answer_turn_ids) for pair in t.qa_pairs] == [(0, (1,)), (2, (3,))]


def test_music_turn_is_skipped_and_same_speaker_answer_turns_are_collected():
    t = topology([
        dict(segment_id=0, speaker="host", text="Why did you leave?", start_seconds=0, end_seconds=1),
        dict(segment_id=1, speaker=None, text="[Music]", start_seconds=1, end_seconds=1.5),
        dict(segment_id=2, speaker="guest", text="I wanted a change.", start_seconds=1.5, end_seconds=2),
        dict(segment_id=3, speaker="guest", text="I found a better fit.", start_seconds=4, end_seconds=5),
    ])
    assert t.qa_pairs[0].answer_turn_ids == (2, 3)
    assert all(t.turns[tid].text != "[Music]" for tid in t.qa_pairs[0].answer_turn_ids)


def test_containing_block_uses_maximum_overlap_and_requires_intersection():
    t = topology([
        dict(segment_id=0, speaker="a", text="First block.", start_seconds=0, end_seconds=4),
        dict(segment_id=1, speaker="b", text="Second block.", start_seconds=10, end_seconds=14),
    ])
    assert t.get_containing_block(3, 11).block_id == 0  # equal overlap, earlier block wins
    assert t.get_containing_block(8, 9) is None
