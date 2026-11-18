"""Adversarial golden-dataset accounting and ClipSelector integration tests."""

import json
import math

import pytest

from lib.eval_studio import (
    EDITORIAL_DIMENSIONS,
    PODCAST_ARCHETYPES,
    BenchmarkReport,
    GoldenDatasetEvaluator,
    GoldenEpisodeFixture,
    GoldClipAnnotation,
    HumanDimensionScore,
    TrapMomentAnnotation,
)
from lib.models.clip_plan import ClipSelectionPlan
from tools.analysis.clip_selector import ClipSelector


def _proposal(candidate_id, text, hook, start, end, *, audit=None):
    return {
        "candidate_id": candidate_id, "start_seconds": start, "end_seconds": end,
        "original_spoken_dialogue": text, "spoken_opening": hook, "spoken_hook_text": hook,
        "editorial_title": f"Title {candidate_id}",
        "cold_viewer_audit": audit or {
            "subject_grounded": True, "entities_resolved": True, "pronouns_resolved": True,
            "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": True,
        },
        "editorial_scores": [{"dimension": "hook_pull", "rationale": "A clear source-grounded opening.", "score": .9}],
    }


def _selector_fixture_and_plan():
    episode_id = "eval-episode"
    texts = [
        "We learned this lesson the hard way, and the actual strategy was focus.",
        "The team went viral overnight after the launch.",
        "That is why it worked in the end.",
    ]
    transcript = {"transcript": [
        {"text": texts[0], "start": 0, "duration": 30},
        {"text": texts[1], "start": 30, "duration": 30},
        {"text": texts[2], "start": 60, "duration": 30},
    ]}
    result = ClipSelector().execute({
        "project_id": episode_id, "source_media_ref": "episode.mp4", "transcript": transcript,
        "transcript_format": "youtube", "min_duration_seconds": 15,
        "max_duration_seconds": 100, "preferred_max_duration_seconds": 80,
        "max_clips": 5, "generated_at": "2026-11-17T12:00:00Z",
        "candidates": [
            _proposal("good", texts[0], "We learned this lesson the hard way", 0, 20),
            _proposal("hallucinated", texts[1], "The product became an overnight sensation", 30, 50),
            _proposal("dangling", texts[2], texts[2], 60, 80, audit={
                "subject_grounded": False, "entities_resolved": True, "pronouns_resolved": False,
                "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": False,
            }),
        ],
    })
    assert result.success, result.error
    raw_plan = result.data["plan"]
    for candidate in raw_plan["candidates"]:
        if candidate["candidate_id"] == "good":
            candidate["review_state"] = "SELECTED_FOR_REVIEW"
    plan = ClipSelectionPlan.model_validate(raw_plan)
    fixture = GoldenEpisodeFixture(
        episode_id=episode_id, title="A grounded lesson", archetype="personal_narrative",
        languages=("en",), transcript_format="youtube", transcript=transcript,
        gold_clips=(GoldClipAnnotation("gold-good", 0, 20, "personal_narrative", expected_hook_substring="We learned this lesson"),),
        trap_moments=(
            TrapMomentAnnotation("trap-hook", 30, 50, "Fabricated hook", "hook_provenance"),
            TrapMomentAnnotation("trap-pronoun", 60, 80, "Unresolved opening referent", "cold_viewer"),
        ),
        human_scores={"reviewer-a": (HumanDimensionScore("standalone_comprehension", 4.0, "The premise is clear."),)},
    )
    return fixture, plan


def _empty_plan(project_id="empty-episode"):
    return ClipSelectionPlan(
        version="1.0", project_id=project_id, source_media_ref="episode.mp4",
        transcript_revision_id="revision", generated_at="2026-11-17T12:00:00Z", candidates=(),
    )


def test_authoritative_dimensions_archetypes_and_strict_annotation_validation():
    assert EDITORIAL_DIMENSIONS == (
        "standalone_comprehension", "context_completeness", "moment_strength", "opening_effectiveness",
        "narrative_coherence", "natural_boundaries", "factual_fidelity", "audio_quality",
        "subtitle_correctness", "visual_quality", "portfolio_diversity", "non_redundancy",
    )
    assert PODCAST_ARCHETYPES == (
        "technical_deep_dive", "solo_monologue", "guest_qa", "comedy_banter", "debate",
        "personal_narrative", "multilingual_hinglish",
    )
    for bad in (0.5, 5.5, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            HumanDimensionScore("audio_quality", bad)
    with pytest.raises(ValueError):
        HumanDimensionScore("virality", 5)
    with pytest.raises(ValueError):
        GoldClipAnnotation("g", True, 2, "debate")
    with pytest.raises(ValueError):
        TrapMomentAnnotation("t", 2, 2, "bad interval", "cold_viewer")
    with pytest.raises(ValueError):
        GoldenEpisodeFixture("e", "bad archetype", "unknown", ("en",), "youtube", {"transcript": []}, ())


def test_fixture_round_trip_preserves_english_devanagari_hinglish_and_unicode(tmp_path):
    multilingual = "English café e\u0301 — हिंदी क़ — Hinglish नमस्ते — 👨‍👩‍👧‍👦"
    fixture = GoldenEpisodeFixture(
        episode_id="unicode-episode", title="Unicode episode", archetype="multilingual_hinglish",
        languages=("en", "hi", "hinglish"), transcript_format="raw_document",
        transcript={"text": multilingual, "segments": [{"text": multilingual}]}, gold_clips=(),
    )
    path = GoldenDatasetEvaluator.save_fixture(fixture, tmp_path / "golden.json")
    loaded = GoldenDatasetEvaluator.load_fixture(path)
    assert loaded == fixture
    assert loaded.transcript["text"] == multilingual
    assert not list(tmp_path.glob("*.tmp"))


def test_greedy_one_to_one_matching_prevents_double_count_and_counts_duplicates():
    fixture, plan = _selector_fixture_and_plan()
    selected = next(item for item in plan.candidates if item.candidate_id == "good")
    duplicate = selected.model_copy(update={
        "candidate_id": "good-overlap", "start_seconds": 1.0, "end_seconds": 21.0,
        "duration_seconds": 20.0,
    })
    expanded = plan.model_copy(update={"candidates": (*plan.candidates, duplicate)})
    metrics = GoldenDatasetEvaluator().evaluate_episode(fixture, expanded)
    assert metrics.gold_matched_count == 1
    assert metrics.gold_recall == 1.0
    assert metrics.selected_precision == 0.5
    assert metrics.duplicate_leak_count == 1


def test_trap_rejection_hallucinated_hook_and_dangling_pronoun_end_to_end():
    fixture, plan = _selector_fixture_and_plan()
    metrics = GoldenDatasetEvaluator().evaluate_episode(fixture, plan)
    assert metrics.gold_recall == 1.0
    assert metrics.trap_rejection_rate == 1.0
    assert metrics.false_positive_traps == ()
    assert metrics.selected_clip_ids == ("good",)
    assert metrics.hook_integrity_rate == 1.0


def test_zero_denominators_and_unrated_dimensions_remain_none():
    fixture = GoldenEpisodeFixture(
        episode_id="empty-episode", title="No annotations", archetype="technical_deep_dive",
        languages=("en",), transcript_format="youtube", transcript={"transcript": []}, gold_clips=(),
    )
    metrics = GoldenDatasetEvaluator().evaluate_episode(fixture, _empty_plan())
    assert metrics.gold_recall is None
    assert metrics.selected_precision is None
    assert metrics.mean_matched_boundary_iou is None
    assert metrics.trap_rejection_rate is None
    assert metrics.hook_integrity_rate is None
    assert set(metrics.dimension_averages) == set(EDITORIAL_DIMENSIONS)
    assert all(value is None for value in metrics.dimension_averages.values())


def test_fabricated_dialogue_and_hook_fail_transcript_span_verification():
    fixture, plan = _selector_fixture_and_plan()
    candidates = []
    for candidate in plan.candidates:
        if candidate.candidate_id == "good":
            fake_hook = candidate.spoken_hook.model_copy(update={"text": "Invented evidence that is absent."})
            candidate = candidate.model_copy(update={
                "original_spoken_dialogue": "Invented evidence that is absent.", "spoken_hook": fake_hook,
            })
        candidates.append(candidate)
    forged_plan = plan.model_copy(update={"candidates": tuple(candidates)})
    metrics = GoldenDatasetEvaluator().evaluate_episode(fixture, forged_plan)
    assert metrics.hook_integrity_rate == 0.0
    assert metrics.gold_hook_match_rate == 0.0


def test_synthetic_golden_podcast_pack_loads_and_evaluates_all_archetypes():
    from pathlib import Path

    root = Path(__file__).parents[1] / "eval" / "golden_podcasts"
    fixtures = tuple(GoldenDatasetEvaluator.load_fixture(path) for path in sorted(root.glob("*.json")))
    assert len(fixtures) == 5
    plans = {fixture.episode_id: _empty_plan(fixture.episode_id) for fixture in fixtures}
    report = GoldenDatasetEvaluator().evaluate_suite(fixtures, plans, run_id="synthetic-pack", generated_at="2026-11-18T00:00:00Z")
    assert report.episode_count == 5
    assert {metric.archetype for metric in report.episode_metrics} == set(PODCAST_ARCHETYPES) - {
        "solo_monologue", "personal_narrative", "comedy_banter"
    } | {"comedy_banter"}


def test_suite_aggregation_atomic_json_markdown_and_ab_report_diff(tmp_path):
    fixture, selected_plan = _selector_fixture_and_plan()
    empty_fixture = GoldenEpisodeFixture(
        episode_id="hinglish-empty", title="Hinglish review pending", archetype="multilingual_hinglish",
        languages=("hi", "hinglish"), transcript_format="vtt", transcript="WEBVTT\n", gold_clips=(),
    )
    empty_plan = _empty_plan("hinglish-empty")
    evaluator = GoldenDatasetEvaluator()
    output_json, output_md = tmp_path / "reports" / "eval_report.json", tmp_path / "reports" / "eval_report.md"
    report = evaluator.evaluate_suite(
        (fixture, empty_fixture), {fixture.episode_id: selected_plan, empty_fixture.episode_id: empty_plan},
        run_id="wave6a", generated_at="2026-11-17T12:00:00Z", config_snapshot={"threshold": .5},
        output_json_path=output_json, output_markdown_path=output_md,
    )
    assert report.episode_count == 2
    assert report.macro_metrics["gold_recall"] == 1.0
    assert report.macro_metrics["selected_precision"] == 1.0
    assert report.macro_metrics["dimension_averages"]["standalone_comprehension"] == 4.0
    assert json.loads(output_json.read_text(encoding="utf-8"))["run_id"] == "wave6a"
    assert "multilingual_hinglish" in output_md.read_text(encoding="utf-8")
    assert not list(output_json.parent.glob("*.tmp"))

    baseline_metrics = dict(report.macro_metrics)
    candidate_metrics = dict(report.macro_metrics)
    baseline_metrics.update({"gold_recall": .5, "duplicate_leak_count": 0.0})
    candidate_metrics.update({"gold_recall": 1.0, "duplicate_leak_count": 1.0})
    baseline_metrics["dimension_averages"] = dict(baseline_metrics["dimension_averages"])
    candidate_metrics["dimension_averages"] = dict(candidate_metrics["dimension_averages"])
    baseline_metrics["dimension_averages"]["standalone_comprehension"] = 2.0
    candidate_metrics["dimension_averages"]["standalone_comprehension"] = 4.0
    baseline = BenchmarkReport("baseline", report.generated_at, report.episode_count, report.episode_metrics, baseline_metrics)
    candidate = BenchmarkReport("candidate", report.generated_at, report.episode_count, report.episode_metrics, candidate_metrics)
    diff = evaluator.compare_reports(baseline, candidate)
    assert "gold_recall" in diff.improvements
    assert "dimension_averages.standalone_comprehension" in diff.improvements
    assert "duplicate_leak_count" in diff.regressions
    assert "candidate − baseline" in diff.to_markdown()


def test_report_comparison_keeps_unmeasured_deltas_none():
    before = {"run_id": "before", "macro_metrics": {"gold_recall": None}}
    after = {"run_id": "after", "macro_metrics": {"gold_recall": 1.0}}
    diff = GoldenDatasetEvaluator().compare_reports(before, after)
    assert diff.metric_deltas["gold_recall"] is None
    assert not diff.improvements and not diff.regressions
