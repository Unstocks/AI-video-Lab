"""Deterministic golden-episode evaluation; metrics describe evidence, not quality claims."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, Optional, Sequence
import unicodedata

from lib.deduplicator import temporal_iou
from lib.models.clip_plan import ClipSelectionPlan


EDITORIAL_DIMENSIONS: tuple[str, ...] = (
    "standalone_comprehension", "context_completeness", "moment_strength",
    "opening_effectiveness", "narrative_coherence", "natural_boundaries",
    "factual_fidelity", "audio_quality", "subtitle_correctness", "visual_quality",
    "portfolio_diversity", "non_redundancy",
)
PODCAST_ARCHETYPES: tuple[str, ...] = (
    "technical_deep_dive", "solo_monologue", "guest_qa", "comedy_banter", "debate",
    "personal_narrative", "multilingual_hinglish",
)
TRANSCRIPT_FORMATS = ("youtube", "whisper", "srt", "vtt", "raw_document")
TRAP_GATES = ("hook_provenance", "cold_viewer", "incomplete_thought", "duration", "duplicate", "media_quality")


def _nonempty(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _time(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _threshold(value: Any, name: str) -> float:
    result = _time(value, name)
    if result > 1:
        raise ValueError(f"{name} must be in [0, 1]")
    return result


@dataclass(frozen=True)
class GoldClipAnnotation:
    gold_id: str
    start_seconds: float
    end_seconds: float
    archetype: str
    notes: str = ""
    expected_hook_substring: Optional[str] = None
    required_context_notes: str = ""

    def __post_init__(self) -> None:
        _nonempty(self.gold_id, "gold_id")
        start, end = _time(self.start_seconds, "start_seconds"), _time(self.end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("gold end_seconds must be greater than start_seconds")
        if self.archetype not in PODCAST_ARCHETYPES:
            raise ValueError(f"unknown podcast archetype {self.archetype!r}")
        if not isinstance(self.notes, str) or not isinstance(self.required_context_notes, str):
            raise ValueError("gold notes must be strings")
        if self.expected_hook_substring is not None and not isinstance(self.expected_hook_substring, str):
            raise ValueError("expected_hook_substring must be a string or None")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True)
class TrapMomentAnnotation:
    trap_id: str
    start_seconds: float
    end_seconds: float
    trap_reason: str
    expected_failure_gate: Literal[
        "hook_provenance", "cold_viewer", "incomplete_thought", "duration", "duplicate", "media_quality"
    ]

    def __post_init__(self) -> None:
        _nonempty(self.trap_id, "trap_id")
        _nonempty(self.trap_reason, "trap_reason")
        start, end = _time(self.start_seconds, "start_seconds"), _time(self.end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("trap end_seconds must be greater than start_seconds")
        if self.expected_failure_gate not in TRAP_GATES:
            raise ValueError(f"unknown trap failure gate {self.expected_failure_gate!r}")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True)
class HumanDimensionScore:
    dimension: str
    score: Optional[float] = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.dimension not in EDITORIAL_DIMENSIONS:
            raise ValueError(f"unknown editorial dimension {self.dimension!r}")
        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
                raise ValueError("score must be a finite number or None")
            if not 1.0 <= self.score <= 5.0:
                raise ValueError("score must be in [1.0, 5.0]")
            object.__setattr__(self, "score", float(self.score))
        if not isinstance(self.rationale, str):
            raise ValueError("rationale must be a string")


@dataclass(frozen=True)
class GoldenEpisodeFixture:
    episode_id: str
    title: str
    archetype: str
    languages: tuple[str, ...]
    transcript_format: Literal["youtube", "whisper", "srt", "vtt", "raw_document"]
    transcript: dict[str, Any] | str
    gold_clips: tuple[GoldClipAnnotation, ...]
    trap_moments: tuple[TrapMomentAnnotation, ...] = ()
    human_scores: dict[str, tuple[HumanDimensionScore, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("episode_id", "title"):
            _nonempty(getattr(self, name), name)
        if self.archetype not in PODCAST_ARCHETYPES:
            raise ValueError(f"unknown podcast archetype {self.archetype!r}")
        if self.transcript_format not in TRANSCRIPT_FORMATS:
            raise ValueError(f"unsupported transcript_format {self.transcript_format!r}")
        if not isinstance(self.languages, tuple) or not self.languages or any(not isinstance(x, str) or not x.strip() for x in self.languages):
            raise ValueError("languages must be a non-empty tuple of non-empty strings")
        if not isinstance(self.transcript, (dict, str)) or (isinstance(self.transcript, str) and not self.transcript.strip()):
            raise ValueError("transcript must be a non-empty dict or string")
        if not isinstance(self.gold_clips, tuple) or any(not isinstance(x, GoldClipAnnotation) for x in self.gold_clips):
            raise ValueError("gold_clips must be a tuple of GoldClipAnnotation")
        if not isinstance(self.trap_moments, tuple) or any(not isinstance(x, TrapMomentAnnotation) for x in self.trap_moments):
            raise ValueError("trap_moments must be a tuple of TrapMomentAnnotation")
        if len({x.gold_id for x in self.gold_clips}) != len(self.gold_clips):
            raise ValueError("gold_id values must be unique within an episode")
        if len({x.trap_id for x in self.trap_moments}) != len(self.trap_moments):
            raise ValueError("trap_id values must be unique within an episode")
        if not isinstance(self.human_scores, dict):
            raise ValueError("human_scores must be a dictionary")
        for key, records in self.human_scores.items():
            if not isinstance(key, str) or not isinstance(records, tuple) or any(not isinstance(x, HumanDimensionScore) for x in records):
                raise ValueError("human_scores values must be tuples of HumanDimensionScore")


@dataclass(frozen=True)
class EpisodeEvalMetrics:
    episode_id: str
    archetype: str
    gold_count: int
    selected_count: int
    gold_matched_count: int
    gold_recall: Optional[float]
    selected_precision: Optional[float]
    mean_matched_boundary_iou: Optional[float]
    trap_count: int
    trap_rejected_count: int
    trap_rejection_rate: Optional[float]
    false_positive_traps: tuple[str, ...]
    duplicate_leak_count: int
    hook_integrity_rate: Optional[float]
    dimension_averages: dict[str, Optional[float]]
    selected_clip_ids: tuple[str, ...]
    matched_pairs: tuple[tuple[str, str, float], ...]

    def __post_init__(self) -> None:
        _nonempty(self.episode_id, "episode_id")
        if self.archetype not in PODCAST_ARCHETYPES:
            raise ValueError(f"unknown podcast archetype {self.archetype!r}")
        for name in ("gold_count", "selected_count", "gold_matched_count", "trap_count", "trap_rejected_count", "duplicate_leak_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.gold_matched_count > min(self.gold_count, self.selected_count):
            raise ValueError("gold_matched_count cannot exceed gold or selected count")
        if self.trap_rejected_count > self.trap_count:
            raise ValueError("trap_rejected_count cannot exceed trap_count")
        for name in ("gold_recall", "selected_precision", "mean_matched_boundary_iou", "trap_rejection_rate", "hook_integrity_rate"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{name} must be a finite ratio in [0, 1] or None")
        if not isinstance(self.dimension_averages, dict) or set(self.dimension_averages) != set(EDITORIAL_DIMENSIONS):
            raise ValueError("dimension_averages must contain exactly the 12 editorial dimensions")
        for value in self.dimension_averages.values():
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 1 <= value <= 5):
                raise ValueError("dimension averages must be in [1, 5] or None")
        if not isinstance(self.false_positive_traps, tuple) or not isinstance(self.selected_clip_ids, tuple) or not isinstance(self.matched_pairs, tuple):
            raise ValueError("metric collections must be tuples")
        for clip_id, gold_id, overlap in self.matched_pairs:
            _nonempty(clip_id, "matched clip_id")
            _nonempty(gold_id, "matched gold_id")
            _threshold(overlap, "matched overlap")


@dataclass(frozen=True)
class BenchmarkReport:
    run_id: str
    generated_at: str
    episode_count: int
    episode_metrics: tuple[EpisodeEvalMetrics, ...]
    macro_metrics: dict[str, Any]
    config_snapshot: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.run_id, "run_id")
        _nonempty(self.generated_at, "generated_at")
        if isinstance(self.episode_count, bool) or not isinstance(self.episode_count, int) or self.episode_count < 0:
            raise ValueError("episode_count must be a nonnegative integer")
        if not isinstance(self.episode_metrics, tuple) or self.episode_count != len(self.episode_metrics):
            raise ValueError("episode_count must match the episode_metrics tuple")
        if not isinstance(self.macro_metrics, dict):
            raise ValueError("macro_metrics must be a dictionary")
        for name, value in self.macro_metrics.items():
            if name == "dimension_averages":
                if not isinstance(value, dict) or set(value) != set(EDITORIAL_DIMENSIONS):
                    raise ValueError("macro dimension_averages must contain all 12 dimensions")
                for dimension_value in value.values():
                    if dimension_value is not None and (
                        isinstance(dimension_value, bool) or not isinstance(dimension_value, (int, float))
                        or not math.isfinite(dimension_value) or not 1 <= dimension_value <= 5
                    ):
                        raise ValueError("macro dimension values must be in [1, 5] or None")
                continue
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"macro metric {name} must be finite or None")
            if name == "duplicate_leak_count" and value < 0:
                raise ValueError("duplicate_leak_count must be nonnegative")
            if name.startswith("dimension_averages.") and not 1 <= value <= 5:
                raise ValueError(f"macro dimension {name} must be in [1, 5]")
            if name != "duplicate_leak_count" and not name.startswith("dimension_averages.") and not 0 <= value <= 1:
                raise ValueError(f"macro ratio {name} must be in [0, 1]")
        if not isinstance(self.config_snapshot, dict):
            raise ValueError("config_snapshot must be a dictionary")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkDiff:
    baseline_run_id: str
    candidate_run_id: str
    metric_deltas: dict[str, Optional[float]]
    improvements: tuple[str, ...]
    regressions: tuple[str, ...]

    def __post_init__(self) -> None:
        _nonempty(self.baseline_run_id, "baseline_run_id")
        _nonempty(self.candidate_run_id, "candidate_run_id")
        if not isinstance(self.metric_deltas, dict):
            raise ValueError("metric_deltas must be a dictionary")
        for name, value in self.metric_deltas.items():
            if not isinstance(name, str) or (value is not None and
                    (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value))):
                raise ValueError("metric deltas must be finite numbers or None")
        if not isinstance(self.improvements, tuple) or not isinstance(self.regressions, tuple):
            raise ValueError("improvements and regressions must be tuples")
        if set(self.improvements) & set(self.regressions):
            raise ValueError("a metric cannot be both an improvement and regression")

    def to_markdown(self) -> str:
        lines = ["# Benchmark Comparison", "", f"- Baseline: `{self.baseline_run_id}`", f"- Candidate: `{self.candidate_run_id}`", "",
                 "| Metric | Delta (candidate − baseline) |", "|---|---:|"]
        for name, delta in sorted(self.metric_deltas.items()):
            lines.append(f"| `{name}` | {'—' if delta is None else f'{delta:+.4f}'} |")
        lines.extend(["", f"Improvements: {', '.join(self.improvements) if self.improvements else 'None measured'}",
                      f"Regressions: {', '.join(self.regressions) if self.regressions else 'None measured'}", ""])
        return "\n".join(lines)


class GoldenDatasetEvaluator:
    """Compare deterministic selected-clip plans with human-annotated episodes."""

    @staticmethod
    def _fixture_from_dict(raw: dict[str, Any]) -> GoldenEpisodeFixture:
        return GoldenEpisodeFixture(
            episode_id=raw["episode_id"], title=raw["title"], archetype=raw["archetype"],
            languages=tuple(raw["languages"]), transcript_format=raw["transcript_format"],
            transcript=raw["transcript"],
            gold_clips=tuple(GoldClipAnnotation(**item) for item in raw.get("gold_clips", [])),
            trap_moments=tuple(TrapMomentAnnotation(**item) for item in raw.get("trap_moments", [])),
            human_scores={key: tuple(HumanDimensionScore(**item) for item in values)
                          for key, values in raw.get("human_scores", {}).items()},
        )

    @classmethod
    def load_fixture(cls, path: str | Path) -> GoldenEpisodeFixture:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("fixture JSON must contain an object")
        return cls._fixture_from_dict(raw)

    @staticmethod
    def _atomic_write(path: str | Path, content: str) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)
        return destination

    @classmethod
    def save_fixture(cls, fixture: GoldenEpisodeFixture, path: str | Path) -> Path:
        if not isinstance(fixture, GoldenEpisodeFixture):
            raise TypeError("fixture must be GoldenEpisodeFixture")
        return cls._atomic_write(path, json.dumps(asdict(fixture), ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _plan(plan: ClipSelectionPlan | dict[str, Any]) -> ClipSelectionPlan:
        try:
            return plan if isinstance(plan, ClipSelectionPlan) else ClipSelectionPlan.model_validate(plan)
        except Exception as exc:
            raise ValueError(f"invalid clip selection plan: {exc}") from exc

    @staticmethod
    def _selected(plan: ClipSelectionPlan) -> list[Any]:
        return [clip for clip in plan.candidates
                if clip.review_state in {"SELECTED_FOR_REVIEW", "HUMAN_APPROVED"}
                and clip.validation_state == "VALID" and clip.eligibility_state == "ELIGIBLE"]

    @staticmethod
    def _hook_is_intact(clip: Any) -> bool:
        hook = getattr(clip, "spoken_hook", None)
        if hook is None or not hook.text.strip() or not hook.source_spans:
            return False
        raw = " ".join(unicodedata.normalize("NFC", clip.original_spoken_dialogue).casefold().split())
        spoken = " ".join(unicodedata.normalize("NFC", hook.text).casefold().split())
        return bool(spoken and spoken in raw)

    def evaluate_episode(
        self, fixture: GoldenEpisodeFixture, plan: ClipSelectionPlan | dict[str, Any], *,
        match_iou_threshold: float = 0.50, trap_overlap_iou_threshold: float = 0.35,
        duplicate_iou_threshold: float = 0.35,
        human_ratings: Optional[Mapping[str, Sequence[HumanDimensionScore]]] = None,
    ) -> EpisodeEvalMetrics:
        if not isinstance(fixture, GoldenEpisodeFixture):
            raise TypeError("fixture must be GoldenEpisodeFixture")
        match_threshold = _threshold(match_iou_threshold, "match_iou_threshold")
        trap_threshold = _threshold(trap_overlap_iou_threshold, "trap_overlap_iou_threshold")
        duplicate_threshold = _threshold(duplicate_iou_threshold, "duplicate_iou_threshold")
        hydrated = self._plan(plan)
        if hydrated.project_id != fixture.episode_id:
            raise ValueError(f"plan project_id {hydrated.project_id!r} does not match fixture episode_id {fixture.episode_id!r}")
        selected = self._selected(hydrated)
        pairs: list[tuple[float, str, str]] = []
        for clip in selected:
            for gold in fixture.gold_clips:
                overlap = temporal_iou(clip.start_seconds, clip.end_seconds, gold.start_seconds, gold.end_seconds)
                if overlap >= match_threshold:
                    pairs.append((overlap, clip.candidate_id, gold.gold_id))
        pairs.sort(key=lambda row: (-row[0], row[1], row[2]))
        used_clips: set[str] = set()
        used_gold: set[str] = set()
        matched: list[tuple[str, str, float]] = []
        for overlap, clip_id, gold_id in pairs:
            if clip_id in used_clips or gold_id in used_gold:
                continue
            used_clips.add(clip_id)
            used_gold.add(gold_id)
            matched.append((clip_id, gold_id, overlap))

        false_positive_traps = tuple(sorted(
            trap.trap_id for trap in fixture.trap_moments
            if any(temporal_iou(clip.start_seconds, clip.end_seconds, trap.start_seconds, trap.end_seconds) >= trap_threshold
                   for clip in selected)
        ))
        trap_rejected = len(fixture.trap_moments) - len(false_positive_traps)
        duplicate_count = sum(
            temporal_iou(left.start_seconds, left.end_seconds, right.start_seconds, right.end_seconds) >= duplicate_threshold
            for index, left in enumerate(selected) for right in selected[index + 1:]
        )
        hook_count = sum(self._hook_is_intact(clip) for clip in selected)
        score_rows: dict[str, list[float]] = {dimension: [] for dimension in EDITORIAL_DIMENSIONS}
        score_sources: list[Sequence[HumanDimensionScore]] = [
            scores for scores in fixture.human_scores.values()
        ]
        if human_ratings is not None:
            if not isinstance(human_ratings, Mapping):
                raise ValueError("human_ratings must be a mapping")
            score_sources.extend(human_ratings.values())
        for records in score_sources:
            for record in records:
                if not isinstance(record, HumanDimensionScore):
                    raise ValueError("human rating entries must be HumanDimensionScore")
                if record.score is not None:
                    score_rows[record.dimension].append(record.score)
        dimension_averages = {
            dimension: (sum(values) / len(values) if values else None)
            for dimension, values in score_rows.items()
        }
        gold_count, selected_count = len(fixture.gold_clips), len(selected)
        return EpisodeEvalMetrics(
            episode_id=fixture.episode_id, archetype=fixture.archetype,
            gold_count=gold_count, selected_count=selected_count, gold_matched_count=len(matched),
            gold_recall=len(matched) / gold_count if gold_count else None,
            selected_precision=len(matched) / selected_count if selected_count else None,
            mean_matched_boundary_iou=(sum(row[2] for row in matched) / len(matched)) if matched else None,
            trap_count=len(fixture.trap_moments), trap_rejected_count=trap_rejected,
            trap_rejection_rate=trap_rejected / len(fixture.trap_moments) if fixture.trap_moments else None,
            false_positive_traps=false_positive_traps, duplicate_leak_count=duplicate_count,
            hook_integrity_rate=hook_count / selected_count if selected_count else None,
            dimension_averages=dimension_averages,
            selected_clip_ids=tuple(clip.candidate_id for clip in selected), matched_pairs=tuple(matched),
        )

    @staticmethod
    def _episode_values(metric: EpisodeEvalMetrics) -> dict[str, Optional[float]]:
        values: dict[str, Optional[float]] = {
            "gold_recall": metric.gold_recall,
            "selected_precision": metric.selected_precision,
            "mean_matched_boundary_iou": metric.mean_matched_boundary_iou,
            "trap_rejection_rate": metric.trap_rejection_rate,
            "duplicate_leak_count": float(metric.duplicate_leak_count),
            "hook_integrity_rate": metric.hook_integrity_rate,
        }
        values.update({f"dimension_averages.{key}": value for key, value in metric.dimension_averages.items()})
        return values

    @staticmethod
    def _markdown(report: BenchmarkReport) -> str:
        lines = [f"# Golden Dataset Evaluation — {report.run_id}", "", f"Generated: {report.generated_at}",
                 f"Episodes: {report.episode_count}", "", "## Macro Metrics", "", "| Metric | Value |", "|---|---:|"]
        flattened = GoldenDatasetEvaluator._flatten_macro(report.macro_metrics)
        for name, value in sorted(flattened.items()):
            lines.append(f"| `{name}` | {'—' if value is None else f'{value:.4f}'} |")
        lines.extend(["", "## Episodes", "", "| Episode | Archetype | Selected | Gold | Recall | Precision | Trap rejection |", "|---|---|---:|---:|---:|---:|---:|"])
        for item in report.episode_metrics:
            fmt = lambda value: "—" if value is None else f"{value:.3f}"
            lines.append(f"| `{item.episode_id}` | `{item.archetype}` | {item.selected_count} | {item.gold_count} | {fmt(item.gold_recall)} | {fmt(item.selected_precision)} | {fmt(item.trap_rejection_rate)} |")
        return "\n".join(lines) + "\n"

    def evaluate_suite(
        self, fixtures: Sequence[GoldenEpisodeFixture], plans_by_episode: Mapping[str, ClipSelectionPlan | dict[str, Any]], *,
        run_id: str, generated_at: Optional[str] = None, config_snapshot: Optional[dict[str, Any]] = None,
        output_json_path: Optional[str | Path] = None, output_markdown_path: Optional[str | Path] = None,
    ) -> BenchmarkReport:
        _nonempty(run_id, "run_id")
        if not isinstance(plans_by_episode, Mapping):
            raise ValueError("plans_by_episode must be a mapping")
        episodes: list[EpisodeEvalMetrics] = []
        seen: set[str] = set()
        for fixture in fixtures:
            if fixture.episode_id in seen:
                raise ValueError(f"duplicate episode_id: {fixture.episode_id}")
            seen.add(fixture.episode_id)
            if fixture.episode_id not in plans_by_episode:
                raise ValueError(f"missing plan for episode {fixture.episode_id!r}")
            episodes.append(self.evaluate_episode(fixture, plans_by_episode[fixture.episode_id]))
        values = [self._episode_values(item) for item in episodes]
        metric_names = ["gold_recall", "selected_precision", "mean_matched_boundary_iou", "trap_rejection_rate",
                        "duplicate_leak_count", "hook_integrity_rate",
                        *(f"dimension_averages.{dim}" for dim in EDITORIAL_DIMENSIONS)]
        flat_macro = {}
        for name in metric_names:
            observed = [row[name] for row in values if row[name] is not None]
            flat_macro[name] = sum(observed) / len(observed) if observed else None
        macro: dict[str, Any] = {
            name: flat_macro[name] for name in metric_names if not name.startswith("dimension_averages.")
        }
        macro["dimension_averages"] = {
            dimension: flat_macro[f"dimension_averages.{dimension}"] for dimension in EDITORIAL_DIMENSIONS
        }
        timestamp = generated_at or datetime.now(timezone.utc).isoformat()
        _nonempty(timestamp, "generated_at")
        report = BenchmarkReport(run_id, timestamp, len(episodes), tuple(episodes), macro, dict(config_snapshot or {}))
        if output_json_path is not None:
            self._atomic_write(output_json_path, json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n")
        if output_markdown_path is not None:
            self._atomic_write(output_markdown_path, self._markdown(report))
        return report

    @staticmethod
    def _report_values(report: BenchmarkReport | dict[str, Any]) -> tuple[str, dict[str, Optional[float]]]:
        if isinstance(report, BenchmarkReport):
            return report.run_id, GoldenDatasetEvaluator._flatten_macro(report.macro_metrics)
        if not isinstance(report, dict) or not isinstance(report.get("macro_metrics"), dict):
            raise ValueError("report must contain macro_metrics")
        return str(report.get("run_id", "unknown")), GoldenDatasetEvaluator._flatten_macro(report["macro_metrics"])

    @staticmethod
    def _flatten_macro(metrics: Mapping[str, Any]) -> dict[str, Optional[float]]:
        flattened: dict[str, Optional[float]] = {}
        for key, value in metrics.items():
            if key == "dimension_averages" and isinstance(value, Mapping):
                flattened.update({f"dimension_averages.{dimension}": score for dimension, score in value.items()})
            elif not isinstance(value, Mapping):
                flattened[key] = value
        return flattened

    def compare_reports(self, baseline: BenchmarkReport | dict[str, Any],
                        candidate: BenchmarkReport | dict[str, Any]) -> BenchmarkDiff:
        baseline_id, before = self._report_values(baseline)
        candidate_id, after = self._report_values(candidate)
        names = sorted(set(before) | set(after))
        deltas: dict[str, Optional[float]] = {}
        improvements: list[str] = []
        regressions: list[str] = []
        higher_is_better = {
            "gold_recall", "selected_precision", "mean_matched_boundary_iou", "trap_rejection_rate",
            "hook_integrity_rate", *(f"dimension_averages.{dim}" for dim in EDITORIAL_DIMENSIONS),
        }
        for name in names:
            left, right = before.get(name), after.get(name)
            delta = float(right) - float(left) if left is not None and right is not None else None
            deltas[name] = delta
            if delta is None or delta == 0:
                continue
            beneficial = delta > 0 if name in higher_is_better else delta < 0
            (improvements if beneficial else regressions).append(name)
        return BenchmarkDiff(baseline_id, candidate_id, deltas, tuple(improvements), tuple(regressions))
