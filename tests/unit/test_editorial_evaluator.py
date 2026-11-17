"""Precedence, ranking, and acoustic integration for editorial evaluation."""

import pytest

from lib.acoustic_profiler import AcousticProfile, AcousticProfiler, EnergyBucket, SilenceInterval, SpeechInterval
from lib.cold_viewer_auditor import ColdViewerAuditor
from lib.editorial_evaluator import CandidateProposal, EditorialEvaluator
from lib.models.clip_plan import ColdViewerAudit, EditorialCriterionScore
from lib.models.transcript import RawTranscriptDocument, RawTranscriptSegment, TimestampProvenance
from lib.transcript_normalizer import TranscriptNormalizer


def clean_audit(**changes):
    data = dict(subject_grounded=True, entities_resolved=True, pronouns_resolved=True,
                premise_to_payoff_complete=True, qualifiers_preserved=True, passed=True)
    data.update(changes)
    return ColdViewerAudit(**data)


def transcript():
    doc = RawTranscriptDocument(segments=(
        RawTranscriptSegment(segment_id=0, speaker="guest", text="We built this product by listening to customers. The result changed everything.", start_seconds=0, end_seconds=30,
                            timing=TimestampProvenance(timing_source="creator_caption", alignment_method="caption_container", evidence_quality="coarse_segment")),
    ))
    return TranscriptNormalizer().normalize(doc)


def proposal(candidate_id="c1", *, start=0, end=20, hook="We built this product", score=0.99,
             audit=None, thought_start=True, thought_end=True, media_usable=True):
    scores = (EditorialCriterionScore(dimension="hook_pull", rationale="Grounded in the opening claim.", score=score),)
    return CandidateProposal(
        candidate_id=candidate_id, start_seconds=start, end_seconds=end,
        original_spoken_dialogue="We built this product by listening to customers.",
        spoken_opening="We built this product", spoken_hook_text=hook,
        editorial_title="What changed the product", cold_viewer_audit=audit or clean_audit(),
        editorial_scores=scores, thought_complete_start=thought_start, thought_complete_end=thought_end,
        media_usable=media_usable,
    )


def test_high_scores_never_rescue_failed_binary_gates():
    proposals = [
        proposal("short", end=10),
        proposal("long", end=130),
        proposal("incomplete", end=20, thought_end=False),
        proposal("cold", end=20, audit=clean_audit(pronouns_resolved=False, passed=False)),
        proposal("hallucination", end=20, hook="The market exploded overnight"),
    ]
    result = EditorialEvaluator().evaluate_candidates(proposals, transcript())
    assert result.eligible_ranked == ()
    reasons = {candidate.clip.candidate_id: (candidate.clip.validation_state, candidate.clip.eligibility_state)
               for candidate in result.rejected}
    assert reasons["short"][1] == "REJECTED_DURATION_OUT_OF_BOUNDS"
    assert reasons["long"][1] == "REJECTED_DURATION_OUT_OF_BOUNDS"
    assert reasons["incomplete"][1] == "REJECTED_INCOMPLETE_THOUGHT"
    assert reasons["cold"][1] == "REJECTED_COLD_VIEWER"
    assert reasons["hallucination"][0] == "INVALID_HOOK_PROVENANCE"
    rejected_hook = next(candidate.clip for candidate in result.rejected if candidate.clip.candidate_id == "hallucination")
    assert rejected_hook.rejection_reason.startswith("hook_validation_failed:")
    assert rejected_hook.spoken_hook.source_spans  # transparent fallback anchor; never eligible


def test_rationale_only_candidate_is_eligible_and_ranks_without_score_cutoff():
    doc = transcript()
    candidate = proposal("rationale", score=None)
    result = EditorialEvaluator().evaluate_candidates([candidate], doc)
    assert len(result.eligible_ranked) == 1
    assert result.eligible_ranked[0].rank_score is None
    assert result.eligible_ranked[0].clip.validation_state == "VALID"


def test_duplicate_candidate_ids_fail_batch_early():
    with pytest.raises(ValueError, match="unique"):
        EditorialEvaluator().evaluate_candidates([proposal("same"), proposal("same")], transcript())


def test_acoustic_refinement_holds_incomplete_boundaries_and_rejects_quiet_audio():
    normalized = transcript()
    acoustic = AcousticProfile(
        audio_path="audio.wav", video_path=None, total_duration_seconds=30,
        silences=(SilenceInterval(0.5, 1.5, 1.0), SilenceInterval(20, 21, 1.0)),
        speech_intervals=(SpeechInterval(0, .5, .5), SpeechInterval(1.5, 20, 18.5), SpeechInterval(21, 30, 9)),
        energy_profile=tuple(EnergyBucket(float(i), -20.0, True) for i in range(30)),
        shot_cuts=(), silence_threshold_db=-35, min_silence_duration_seconds=.25,
        timing_provenance=TimestampProvenance(timing_source="vad_region", alignment_method="vad_energy_or_neural",
                                              evidence_quality="medium_word", uncertainty_seconds=.05),
    )
    evaluator = EditorialEvaluator(min_duration_seconds=5, max_duration_seconds=120,
                                   preferred_max_duration_seconds=90, acoustic_profiler=AcousticProfiler())
    complete = proposal("complete", start=1.2, end=20.2, thought_start=True, thought_end=True)
    held = proposal("held", start=1.2, end=20.2, thought_start=False, thought_end=True)
    result = evaluator.evaluate_candidates([complete, held], normalized, acoustic_profile=acoustic)
    assert len(result.eligible_ranked) == 1
    by_id = {item.clip.candidate_id: item for item in result.eligible_ranked}
    assert by_id["complete"].clip.start_seconds == pytest.approx(1.42)
    assert by_id["complete"].clip.end_seconds == pytest.approx(20.08)
    assert by_id["complete"].clip.start_provenance.original_seconds == 1.2
    held_result = next(item for item in result.rejected if item.clip.candidate_id == "held")
    assert held_result.clip.start_seconds == 1.2
    assert held_result.clip.start_provenance.transformation == "raw_unmodified"
    assert held_result.clip.eligibility_state == "REJECTED_INCOMPLETE_THOUGHT"

    quiet = AcousticProfile(
        audio_path="silent.wav", video_path=None, total_duration_seconds=30, silences=(),
        speech_intervals=(), energy_profile=tuple(EnergyBucket(float(i), -120, False) for i in range(30)),
        shot_cuts=(), silence_threshold_db=-35, min_silence_duration_seconds=.25,
        timing_provenance=acoustic.timing_provenance,
    )
    failed = evaluator.evaluate_candidates([proposal("quiet")], normalized, acoustic_profile=quiet)
    assert failed.rejected[0].clip.eligibility_state == "REJECTED_MEDIA_QUALITY"


def test_invalid_timestamp_proposals_are_reported_without_fabricating_clip_models():
    invalid = proposal("bad-times", start=10, end=10)
    result = EditorialEvaluator().evaluate_candidates([invalid], transcript())
    assert result.rejected == ()
    assert any("invalid timestamps cannot be represented" in warning for warning in result.warnings)
