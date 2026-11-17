"""Structural cold-viewer comprehension and context expansion checks."""

from lib.cold_viewer_auditor import ColdViewerAuditor
from lib.conversation_structure import ConversationTopology, QuestionAnswerPair, SpeakerTurn
from lib.models.clip_plan import ColdViewerAudit
from lib.models.transcript import RawTranscriptDocument


def audit(**overrides):
    values = dict(subject_grounded=True, entities_resolved=True, pronouns_resolved=True,
                  premise_to_payoff_complete=True, qualifiers_preserved=True, passed=True)
    values.update(overrides)
    return ColdViewerAudit(**values)


def question_topology(answer_start=3, answer_end=20):
    doc = RawTranscriptDocument(segments=())
    turns = (
        SpeakerTurn(0, "host", (0,), 0, 2, "Why did he quit?", 0, 10, 4, True),
        SpeakerTurn(1, "guest", (1,), answer_start, answer_end, "Yes, because he quit.", 11, 32, 5, False),
    )
    pair = QuestionAnswerPair(0, (1,), 0, answer_end)
    return ConversationTopology(doc.transcript_revision_id, turns, (pair,), (), answer_end, ("host", "guest"), True)


def test_clean_self_contained_clip_passes_all_five_checks():
    result = ColdViewerAuditor().audit(
        spoken_opening="The team cut onboarding time in half.",
        original_spoken_dialogue="The team cut onboarding time in half.",
        start_seconds=0, end_seconds=20, proposed_audit=audit())
    assert result.passed and result.audit.passed and result.failure_reasons == ()


def test_dangling_english_hinglish_and_devanagari_openings_fail_with_context_hint():
    for opening in ("That's why he quit the company.", "Isliye usne startup chhod diya.",
                    "इसीलिए उसने कंपनी छोड़ दी।"):
        result = ColdViewerAuditor().audit(
            spoken_opening=opening, original_spoken_dialogue=opening,
            start_seconds=3, end_seconds=20, proposed_audit=audit(), topology=question_topology())
        assert not result.passed
        assert result.audit.pronouns_resolved is False
        assert result.recommended_context_start_seconds == 0
        assert any("unresolved opening" in reason for reason in result.failure_reasons)


def test_explicit_editorial_framing_allows_anaphoric_opening():
    result = ColdViewerAuditor().audit(
        spoken_opening="That's why he quit the company.",
        original_spoken_dialogue="That's why he quit the company.",
        start_seconds=3, end_seconds=20, proposed_audit=audit(),
        editorial_framing="Talking about Sam's 2023 board exit")
    assert result.passed and result.audit.pronouns_resolved


def test_mid_answer_fragment_requires_triggering_question():
    result = ColdViewerAuditor().audit(
        spoken_opening="Yes, because we burned through our runway.",
        original_spoken_dialogue="Yes, because we burned through our runway.",
        start_seconds=3, end_seconds=20, proposed_audit=audit(), topology=question_topology())
    assert not result.passed
    assert result.audit.subject_grounded is False
    assert result.recommended_context_start_seconds == 0
    assert "clip starts mid-answer" in result.failure_reasons[0]


def test_required_context_over_duration_limit_marks_moment_episodic():
    result = ColdViewerAuditor().audit(
        spoken_opening="Yes, because it changed everything.",
        original_spoken_dialogue="Yes, because it changed everything.",
        start_seconds=150, end_seconds=180, proposed_audit=audit(), topology=question_topology(150, 180))
    assert result.recommended_context_start_seconds == 0
    assert result.inherently_episodic
    assert any("exceeds max_duration_seconds" in warning for warning in result.warnings)


def test_existing_false_checks_remain_failed_and_are_named():
    result = ColdViewerAuditor().audit(
        spoken_opening="An understandable opening.", original_spoken_dialogue="An understandable opening.",
        start_seconds=0, end_seconds=5,
        proposed_audit=audit(entities_resolved=False, qualifiers_preserved=False, passed=False))
    assert not result.passed
    assert "cold-viewer check failed: entities_resolved" in result.failure_reasons
    assert "cold-viewer check failed: qualifiers_preserved" in result.failure_reasons
