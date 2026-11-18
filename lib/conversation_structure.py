"""Deterministic speaker turns, Q&A pairs, and coarse conversation blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from lib.transcript_normalizer import NormalizedSentence, NormalizedTranscriptResult


@dataclass(frozen=True)
class SpeakerTurn:
    turn_id: int
    speaker: Optional[str]
    sentence_ids: tuple[int, ...]
    start_seconds: float
    end_seconds: float
    text: str
    norm_start: int
    norm_end: int
    word_count: int
    is_question: bool


@dataclass(frozen=True)
class QuestionAnswerPair:
    question_turn_id: int
    answer_turn_ids: tuple[int, ...]
    start_seconds: float
    end_seconds: float


@dataclass(frozen=True)
class ConversationalBlock:
    block_id: int
    turn_ids: tuple[int, ...]
    start_seconds: float
    end_seconds: float
    speakers: tuple[str, ...]
    qa_pairs: tuple[QuestionAnswerPair, ...]
    word_count: int
    dominant_speaker: Optional[str]


@dataclass(frozen=True)
class ConversationTopology:
    transcript_revision_id: str
    turns: tuple[SpeakerTurn, ...]
    qa_pairs: tuple[QuestionAnswerPair, ...]
    blocks: tuple[ConversationalBlock, ...]
    total_duration_seconds: float
    unique_speakers: tuple[str, ...]
    has_speaker_diarization: bool

    def get_context_window(self, start_seconds: float, end_seconds: float, *, before_seconds: float = 90.0, after_seconds: float = 30.0) -> tuple[SpeakerTurn, ...]:
        lo, hi = start_seconds - before_seconds, end_seconds + after_seconds
        return tuple(t for t in self.turns if t.end_seconds >= lo and t.start_seconds <= hi)

    def find_preceding_question(self, turn_id: int, max_lookback_seconds: float = 45.0) -> Optional[SpeakerTurn]:
        target = next((t for t in self.turns if t.turn_id == turn_id), None)
        if target is None:
            return None
        return next((t for t in reversed(self.turns) if t.is_question and t.end_seconds <= target.start_seconds and target.start_seconds - t.end_seconds <= max_lookback_seconds), None)

    def get_containing_block(self, start_seconds: float, end_seconds: float) -> Optional[ConversationalBlock]:
        overlaps = [(min(b.end_seconds, end_seconds) - max(b.start_seconds, start_seconds), b.block_id, b)
                    for b in self.blocks]
        overlaps = [item for item in overlaps if item[0] > 0]
        return min(overlaps, key=lambda item: (-item[0], item[1]))[2] if overlaps else None


@dataclass(frozen=True)
class CandidateWindowSeed:
    seed_id: str
    start_seconds: float
    end_seconds: float
    source_kind: str
    evidence_turn_ids: tuple[int, ...]
    transcript_revision_id: str




_QUESTION_START = re.compile(
    r"^(?:(?:what|why|how|when|who|where|which|do you|did you|can you|could you|is it|are you|kya|kyun|kaise|kab|kaun|kahan)(?:$|\s|[?!])|"
    r"(?:क्या|क्यों|कैसे|कब|कौन|कहाँ|कहां)(?:$|\s|[?!।॥]))",
    re.I,
)


class ConversationStructureAnalyzer:
    def __init__(self, *, pause_block_gap_seconds: float = 4.0, turn_pause_gap_seconds: float = 1.8):
        self.pause_block_gap_seconds = pause_block_gap_seconds
        self.turn_pause_gap_seconds = turn_pause_gap_seconds

    @staticmethod
    def _is_question(text: str) -> bool:
        for sentence in text.split("\n"):
            candidate = sentence.strip()
            if candidate.endswith("?") or _QUESTION_START.match(candidate):
                return True
        return text.rstrip().endswith("?") or bool(_QUESTION_START.match(text.strip()))

    def analyze(self, transcript: NormalizedTranscriptResult) -> ConversationTopology:
        sentences = transcript.sentences
        non_speech_ids = set(transcript.non_speech_segment_ids)

        def is_non_speech(sentence: NormalizedSentence) -> bool:
            return bool(sentence.source_spans) and all(span.segment_id in non_speech_ids for span in sentence.source_spans)

        non_speech_sentences = {sentence.sentence_id for sentence in sentences if is_non_speech(sentence)}
        groups: list[list[NormalizedSentence]] = []
        for sentence in sentences:
            if not groups:
                groups.append([sentence]); continue
            prior = groups[-1][-1]
            same_speaker = sentence.speaker == prior.speaker
            gap = sentence.start_seconds - prior.end_seconds
            if same_speaker and gap <= self.turn_pause_gap_seconds:
                groups[-1].append(sentence)
            else:
                groups.append([sentence])
        turns = []
        for i, group in enumerate(groups):
            texts = " ".join(s.text for s in group)
            turns.append(SpeakerTurn(i, group[0].speaker, tuple(s.sentence_id for s in group), group[0].start_seconds, group[-1].end_seconds,
                texts, group[0].norm_start, group[-1].norm_end, len(texts.split()),
                any(self._is_question(sentence.text) for sentence in group)))
        qa = []
        for i, turn in enumerate(turns[:-1]):
            if turn.is_question:
                answer_turns = []
                for answer in turns[i + 1:]:
                    if answer.start_seconds - (answer_turns[-1].end_seconds if answer_turns else turn.end_seconds) > self.pause_block_gap_seconds:
                        break
                    answer_is_non_speech = all(sid in non_speech_sentences for sid in answer.sentence_ids)
                    if answer_is_non_speech:
                        continue
                    if answer.is_question or (answer.speaker == turn.speaker and turn.speaker is not None):
                        break
                    if answer.text.strip():
                        answer_turns.append(answer)
                if answer_turns:
                    qa.append(QuestionAnswerPair(turn.turn_id, tuple(t.turn_id for t in answer_turns),
                                                 turn.start_seconds, answer_turns[-1].end_seconds))
        groups_of_turns: list[list[SpeakerTurn]] = []
        for turn in turns:
            if groups_of_turns and turn.start_seconds - groups_of_turns[-1][-1].end_seconds <= self.pause_block_gap_seconds:
                groups_of_turns[-1].append(turn)
            else:
                groups_of_turns.append([turn])
        blocks = []
        for i, group in enumerate(groups_of_turns):
            ids = {t.turn_id for t in group}
            block_qa = tuple(pair for pair in qa if pair.question_turn_id in ids)
            speakers = tuple(dict.fromkeys(t.speaker for t in group if t.speaker))
            counts = {speaker: sum(t.word_count for t in group if t.speaker == speaker) for speaker in speakers}
            dominant = max(counts, key=counts.get) if counts else None
            blocks.append(ConversationalBlock(i, tuple(t.turn_id for t in group), group[0].start_seconds, group[-1].end_seconds,
                speakers, block_qa, sum(t.word_count for t in group), dominant))
        speakers = tuple(dict.fromkeys(t.speaker for t in turns if t.speaker))
        duration = max((s.end_seconds for s in sentences), default=0.0)
        return ConversationTopology(transcript.raw_document.transcript_revision_id or "", tuple(turns), tuple(qa), tuple(blocks), duration, speakers, bool(speakers))

    def propose_candidate_windows(
        self, normalized: NormalizedTranscriptResult, topology: ConversationTopology,
        acoustic_profile=None, *, min_duration_seconds: float = 15.0, max_duration_seconds: float = 90.0,
    ) -> tuple[CandidateWindowSeed, ...]:
        """Propose deterministic, evidence-backed Q&A and monologue windows."""
        for value, name in ((min_duration_seconds, "min_duration_seconds"), (max_duration_seconds, "max_duration_seconds")):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be positive")
        if max_duration_seconds < min_duration_seconds:
            raise ValueError("max_duration_seconds must be >= min_duration_seconds")
        turn_by_id = {turn.turn_id: turn for turn in topology.turns}
        proposals: list[tuple[float, float, str, tuple[int, ...]]] = []
        for pair in topology.qa_pairs:
            turn_ids = (pair.question_turn_id, *pair.answer_turn_ids)
            proposals.append((pair.start_seconds, pair.end_seconds, "qa_pair", turn_ids))
        for block in topology.blocks:
            if block.qa_pairs:
                continue
            proposals.append((block.start_seconds, block.end_seconds, "monologue_arc", block.turn_ids))
        boundaries = sorted({point for sentence in normalized.sentences
                             for point in (sentence.start_seconds, sentence.end_seconds)})
        silences = getattr(acoustic_profile, "silences", ()) if acoustic_profile is not None else ()

        def snap(value: float) -> float:
            nearby_sentences = [point for point in boundaries if abs(point - value) <= 1.5]
            if nearby_sentences:
                value = min(nearby_sentences, key=lambda point: (abs(point - value), point))
            if silences:
                nearby = []
                for silence in silences:
                    for point in (silence.start_seconds, silence.end_seconds):
                        if abs(point - value) <= 1.0:
                            nearby.append((abs(point - value), point))
                if nearby:
                    value = min(nearby)[1]
            return max(0.0, float(value))

        seeds = []
        seen = set()
        for start, end, kind, turn_ids in proposals:
            start, end = snap(start), snap(end)
            if end - start < min_duration_seconds or end - start > max_duration_seconds:
                continue
            key = (round(start, 3), round(end, 3), kind)
            if key in seen:
                continue
            seen.add(key)
            seeds.append(CandidateWindowSeed(
                seed_id=f"window-{len(seeds) + 1:03d}", start_seconds=start, end_seconds=end,
                source_kind=kind, evidence_turn_ids=tuple(turn_ids),
                transcript_revision_id=topology.transcript_revision_id,
            ))
        return tuple(seeds)
