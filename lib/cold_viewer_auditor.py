"""Deterministic structural checks for cold-viewer clip comprehension."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from lib.models.clip_plan import ColdViewerAudit

if TYPE_CHECKING:
    from lib.conversation_structure import ConversationTopology


@dataclass(frozen=True)
class ColdViewerAuditResult:
    audit: ColdViewerAudit
    passed: bool
    failure_reasons: tuple[str, ...] = ()
    recommended_context_start_seconds: Optional[float] = None
    inherently_episodic: bool = False
    warnings: tuple[str, ...] = ()


_DANGLING_ENGLISH = re.compile(
    r"^(?:(?:and\s+|so\s+|but\s+)?(?:that(?:'s| is| was)\s+why|this\s+is\s+why|"
    r"because\s+of\s+(?:this|that)|(?:he|she|they)\s+(?:said|did|quit|left|told|was|were|is|are)|"
    r"it\s+(?:was|is)\s+because))\b", re.I)
_DANGLING_HINGLISH = re.compile(
    r"^(?:(?:aur\s+|toh\s+)?(?:isliye\s+(?:usne|unhone|woh|ye|yeh)|woh\s+isliye|usne\s+bola))\b", re.I)
_DANGLING_HINDI = re.compile(
    r"^(?:(?:और\s+|तो\s+)?(?:इसीलिए\s+(?:उसने|उन्होंने|वह|यह)|वह\s+इसीलिए|उसने\s+कहा))(?=$|\s|[,.?!।])")
_ANSWER_FRAGMENT = re.compile(r"^(?:yes|no|yeah|yep|nope|exactly|right|absolutely|because|haan|nahi|bilkul)\b", re.I)
_ANSWER_FRAGMENT_HINDI = re.compile(r"^(?:हाँ|हां|नहीं|बिल्कुल|क्योंकि)(?=$|\s|[,.?!।])")


class ColdViewerAuditor:
    def __init__(self, *, max_duration_seconds: float = 120.0,
                 question_lookback_seconds: float = 45.0) -> None:
        self.max_duration_seconds = self._positive_finite(max_duration_seconds, "max_duration_seconds")
        self.question_lookback_seconds = self._positive_finite(question_lookback_seconds, "question_lookback_seconds")

    @staticmethod
    def _positive_finite(value: float, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite number greater than zero")
        return float(value)

    @staticmethod
    def _is_dangling_opening(text: str) -> bool:
        opening = text.lstrip(" \t\r\n\"'“‘([{`).")
        return bool(_DANGLING_ENGLISH.search(opening) or _DANGLING_HINGLISH.search(opening)
                    or _DANGLING_HINDI.search(opening))

    def audit(self, *, spoken_opening: str, original_spoken_dialogue: str,
              start_seconds: float, end_seconds: float, proposed_audit: ColdViewerAudit,
              editorial_framing: Optional[str] = None,
              topology: Optional["ConversationTopology"] = None) -> ColdViewerAuditResult:
        if isinstance(start_seconds, bool) or not isinstance(start_seconds, (int, float)) \
                or not math.isfinite(start_seconds) or start_seconds < 0:
            raise ValueError("start_seconds must be a finite nonnegative number")
        start = float(start_seconds)
        end = self._positive_finite(end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        if not isinstance(proposed_audit, ColdViewerAudit):
            proposed_audit = ColdViewerAudit.model_validate(proposed_audit)

        subject = proposed_audit.subject_grounded
        entities = proposed_audit.entities_resolved
        pronouns = proposed_audit.pronouns_resolved
        premise = proposed_audit.premise_to_payoff_complete
        qualifiers = proposed_audit.qualifiers_preserved
        flags = {
            "subject_grounded": subject,
            "entities_resolved": entities,
            "pronouns_resolved": pronouns,
            "premise_to_payoff_complete": premise,
            "qualifiers_preserved": qualifiers,
        }
        reasons = [f"cold-viewer check failed: {name}" for name, value in flags.items() if not value]
        warnings: list[str] = []
        if not proposed_audit.passed and not reasons:
            reasons.append("proposed cold-viewer audit marked as failed")

        recommended_start: Optional[float] = None
        framing_supplied = bool(editorial_framing and editorial_framing.strip())
        if not framing_supplied and not proposed_audit.context_expansion_applied and self._is_dangling_opening(spoken_opening):
            pronouns = False
            flags["pronouns_resolved"] = False
            message = "unresolved opening pronoun/anaphora without context expansion or editorial framing"
            if message not in reasons:
                reasons.append(message)
            if topology is not None:
                context = topology.get_context_window(start, end, before_seconds=self.question_lookback_seconds,
                                                      after_seconds=0.0)
                prior = [turn for turn in context if turn.end_seconds <= start + 0.25]
                questions = [turn for turn in prior if turn.is_question]
                candidate = (questions or prior)
                if candidate:
                    recommended_start = candidate[-1].start_seconds

        if not framing_supplied and topology is not None:
            turns = {turn.turn_id: turn for turn in topology.turns}
            opening_turn = next((turn for turn in topology.turns
                                 if turn.start_seconds <= start < turn.end_seconds), None)
            if opening_turn is not None and (_ANSWER_FRAGMENT.search(spoken_opening.strip())
                                             or _ANSWER_FRAGMENT_HINDI.search(spoken_opening.strip())):
                for pair in topology.qa_pairs:
                    question = turns.get(pair.question_turn_id)
                    if opening_turn.turn_id in pair.answer_turn_ids and question is not None \
                            and question.start_seconds < start and question.end_seconds <= start:
                        subject = False
                        flags["subject_grounded"] = False
                        message = "clip starts mid-answer without triggering question or editorial framing"
                        if message not in reasons:
                            reasons.append(message)
                        recommended_start = question.start_seconds
                        break

        episodic = False
        if recommended_start is not None and end - recommended_start > self.max_duration_seconds:
            episodic = True
            warnings.append("required context expansion exceeds max_duration_seconds; moment is inherently episodic")

        passed = all(flags.values()) and proposed_audit.passed and not reasons
        diagnostics = "; ".join(dict.fromkeys([*reasons, *warnings]))
        notes = "; ".join(filter(None, (proposed_audit.notes, diagnostics)))
        audit = ColdViewerAudit(
            subject_grounded=subject, entities_resolved=entities, pronouns_resolved=pronouns,
            premise_to_payoff_complete=premise, qualifiers_preserved=qualifiers,
            passed=passed, notes=notes, context_expansion_applied=proposed_audit.context_expansion_applied,
        )
        return ColdViewerAuditResult(audit, passed, tuple(dict.fromkeys(reasons)), recommended_start,
                                     episodic, tuple(warnings))
