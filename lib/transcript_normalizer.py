"""Pure multi-format transcript ingestion and exact Unicode offset alignment."""

from __future__ import annotations

import html
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Mapping, Optional, Sequence

from lib.models.transcript import (
    AlignmentMethod, BoundaryTransformation, EvidenceQuality, RawTranscriptDocument,
    RawTranscriptSegment, SourceSpan, TimestampProvenance, TimingSource,
)


@dataclass(frozen=True)
class WordTimingRecord:
    text: str
    start_seconds: float
    end_seconds: float
    confidence: Optional[float] = None


@dataclass(frozen=True)
class NormalizedSegment:
    segment_id: int
    speaker: Optional[str]
    text: str
    start_seconds: float
    end_seconds: float
    norm_start: int
    norm_end: int
    timing_provenance: TimestampProvenance
    words: tuple[WordTimingRecord, ...] = ()
    is_non_speech: bool = False


@dataclass(frozen=True)
class NormalizedSentence:
    sentence_id: int
    text: str
    norm_start: int
    norm_end: int
    source_spans: tuple[SourceSpan, ...]
    speaker: Optional[str]
    speakers: tuple[str, ...]
    start_seconds: float
    end_seconds: float
    timing_provenance: TimestampProvenance


@dataclass(frozen=True)
class _MappedChar:
    segment_id: Optional[int]
    raw_start: Optional[int]
    raw_end: Optional[int]


@dataclass(frozen=True)
class NormalizedTranscriptResult:
    raw_document: RawTranscriptDocument
    normalized_text: str
    segments: tuple[NormalizedSegment, ...]
    sentences: tuple[NormalizedSentence, ...]
    alignment_index: "OffsetAlignmentIndex"
    warnings: tuple[str, ...] = ()
    non_speech_segment_ids: tuple[int, ...] = ()

    def map_normalized_span_to_raw(self, norm_start: int, norm_end: int) -> list[SourceSpan]:
        return self.alignment_index.map_normalized_span_to_raw(norm_start, norm_end)

    def map_raw_span_to_normalized(self, segment_id: int, char_start: int, char_end: int):
        return self.alignment_index.map_raw_span_to_normalized(segment_id, char_start, char_end)

    def extract_raw_slices(self, spans: Sequence[SourceSpan]) -> list[str]:
        return self.alignment_index.extract_raw_slices(spans)


class OffsetAlignmentIndex:
    """Bidirectional normalized-codepoint to immutable raw-codepoint mapping."""

    def __init__(self, document: RawTranscriptDocument, normalized_text: str, chars: Sequence[_MappedChar], segment_order: Mapping[int, int]):
        self.document = document
        self.normalized_text = normalized_text
        self._chars = tuple(chars)
        self._raw_by_id = {s.segment_id: s for s in document.segments}
        self._segment_order = dict(segment_order)

    def map_normalized_span_to_raw(self, norm_start: int, norm_end: int) -> list[SourceSpan]:
        if not (0 <= norm_start <= norm_end <= len(self.normalized_text)):
            raise ValueError("normalized span is out of bounds")
        result: list[SourceSpan] = []
        for char in self._chars[norm_start:norm_end]:
            if char.segment_id is None:
                continue
            if result and result[-1].segment_id == char.segment_id and char.raw_start <= result[-1].char_end:
                prev = result[-1]
                result[-1] = SourceSpan(
                    transcript_revision_id=prev.transcript_revision_id, segment_id=prev.segment_id,
                    char_start=prev.char_start, char_end=max(prev.char_end, char.raw_end), gap_before=prev.gap_before,
                )
            else:
                gap = None
                if result and self._segment_order.get(char.segment_id, -1) > self._segment_order.get(result[-1].segment_id, -1) + 1:
                    gap = "[omitted transcript segment]"
                result.append(SourceSpan(
                    transcript_revision_id=self.document.transcript_revision_id,
                    segment_id=char.segment_id, char_start=char.raw_start, char_end=char.raw_end,
                    gap_before=gap,
                ))
        return result

    def map_raw_span_to_normalized(self, segment_id: int, char_start: int, char_end: int) -> Optional[tuple[int, int]]:
        segment = self._raw_by_id.get(segment_id)
        if segment is None or not (0 <= char_start <= char_end <= len(segment.text)):
            raise ValueError("raw span is out of bounds")
        hits = [i for i, c in enumerate(self._chars) if c.segment_id == segment_id and c.raw_start < char_end and c.raw_end > char_start]
        return (hits[0], hits[-1] + 1) if hits else None

    def extract_raw_slices(self, spans: Sequence[SourceSpan]) -> list[str]:
        slices = []
        for span in spans:
            if span.transcript_revision_id != self.document.transcript_revision_id:
                raise ValueError("transcript revision mismatch")
            segment = self._raw_by_id.get(span.segment_id)
            if segment is None or span.char_end > len(segment.text):
                raise ValueError("source span is out of bounds")
            slices.append(segment.text[span.char_start:span.char_end])
        return slices


_NON_SPEECH = re.compile(r"^\[(?:music|applause|laughter|inaudible|crosstalk|silence)\]$", re.I)
_TIMESTAMP = re.compile(r"(?:(\d{2,}):)?(\d{2}):(\d{2})[,.](\d{1,3})")


def _normalize_segment_text(raw_text: str, *, decode_entities: bool = True) -> tuple[str, tuple[_MappedChar, ...]]:
    """Expand entities, then collapse whitespace and NFC-normalize mapped clusters."""
    atoms: list[tuple[str, int, int]] = []
    i = 0
    while i < len(raw_text):
        if decode_entities and raw_text[i] == "&":
            match = re.match(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);", raw_text[i:])
            if match:
                j = i + len(match.group(0))
                decoded = html.unescape(match.group(0))
                if decoded != match.group(0):
                    atoms.extend((ch, i, j) for ch in decoded)
                    i = j
                    continue
        atoms.append((raw_text[i], i, i + 1))
        i += 1

    units: list[tuple[str, int, int]] = []
    i = 0
    while i < len(atoms):
        ch, raw_start, raw_end = atoms[i]
        if ch.isspace():
            j = i + 1
            while j < len(atoms) and atoms[j][0].isspace():
                j += 1
            units.append((" ", raw_start, atoms[j - 1][2]))
            i = j
            continue
        j = i + 1
        while j < len(atoms):
            nxt = atoms[j][0]
            if unicodedata.category(nxt).startswith("M") or unicodedata.combining(nxt):
                j += 1
                continue
            if nxt == "\u200d" and j + 1 < len(atoms):
                j += 2
                continue
            break
        cluster = unicodedata.normalize("NFC", "".join(atom[0] for atom in atoms[i:j]))
        units.extend((out_ch, raw_start, atoms[j - 1][2]) for out_ch in cluster)
        i = j
    # Trim segment edge spaces without changing source offsets.
    while units and units[0][0] == " ":
        units.pop(0)
    while units and units[-1][0] == " ":
        units.pop()
    return "".join(u[0] for u in units), tuple(_MappedChar(0, u[1], u[2]) for u in units)


class TranscriptNormalizer:
    def __init__(self, *, decode_caption_entities: bool = True, pause_sentence_gap_seconds: float = 1.8):
        self.decode_caption_entities = decode_caption_entities
        self.pause_sentence_gap_seconds = pause_sentence_gap_seconds

    def from_youtube_captions(self, payload: dict) -> RawTranscriptDocument:
        source: TimingSource = "auto_caption" if payload.get("is_auto_generated", False) else "creator_caption"
        segments = []
        for i, item in enumerate(payload.get("transcript", [])):
            start = float(item.get("start", 0.0))
            duration = max(0.0, float(item.get("duration", 0.0)))
            segments.append(RawTranscriptSegment(
                segment_id=i, text=str(item.get("text", "")), start_seconds=start,
                end_seconds=start + duration, speaker=None,
                timing=TimestampProvenance(timing_source=source, alignment_method="caption_container", evidence_quality="coarse_segment"),
            ))
        return RawTranscriptDocument(segments=tuple(segments))

    def from_whisper_transcript(self, payload: dict) -> RawTranscriptDocument:
        segments = []
        for i, item in enumerate(payload.get("segments", [])):
            segment_id = int(item.get("id", i))
            words = self.extract_whisper_words({"segments": [item]}).get(segment_id, ())
            probs = [w.confidence for w in words if w.confidence is not None]
            confidence = sum(probs) / len(probs) if probs else None
            segments.append(RawTranscriptSegment(
                segment_id=segment_id, speaker=item.get("speaker"), text=str(item.get("text", "")),
                start_seconds=float(item.get("start", 0.0)), end_seconds=float(item.get("end", item.get("start", 0.0))),
                timing=TimestampProvenance(timing_source="asr_word" if words else "asr_segment", alignment_method="asr_cross_attention", evidence_quality="medium_word" if words else "coarse_segment", confidence=confidence),
                confidence=confidence,
            ))
        return RawTranscriptDocument(segments=tuple(segments))

    @staticmethod
    def _finite_probability(value: object) -> Optional[float]:
        if isinstance(value, bool):
            return None
        try:
            result = float(value)
            return result if math.isfinite(result) and 0 <= result <= 1 else None
        except (TypeError, ValueError, OverflowError):
            return None

    def extract_whisper_words(self, payload: dict) -> dict[int, tuple[WordTimingRecord, ...]]:
        words_by_segment: dict[int, tuple[WordTimingRecord, ...]] = {}
        for index, segment in enumerate(payload.get("segments", [])):
            segment_id = int(segment.get("id", index))
            records = []
            for word in segment.get("words", []):
                if "start" not in word or "end" not in word:
                    continue
                if isinstance(word["start"], bool) or isinstance(word["end"], bool):
                    continue
                try:
                    start, end = float(word["start"]), float(word["end"])
                except (TypeError, ValueError, OverflowError):
                    continue
                if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                    continue
                records.append(WordTimingRecord(str(word.get("word", word.get("text", ""))), start, end,
                                                self._finite_probability(word.get("probability"))))
            if records:
                words_by_segment[segment_id] = tuple(records)
        return words_by_segment

    def from_srt_or_vtt(self, content: str, *, timing_source: TimingSource = "unknown") -> RawTranscriptDocument:
        cleaned = content.lstrip("\ufeff").strip()
        blocks = re.split(r"\r?\n\s*\r?\n", cleaned) if cleaned else []
        segments = []
        for block in blocks:
            lines = block.splitlines()
            time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
            if time_index is None:
                continue
            pair = lines[time_index].split("-->", 1)
            start, end = self._parse_time(pair[0]), self._parse_time(pair[1].split()[0])
            text = "\n".join(lines[time_index + 1:])
            segments.append(RawTranscriptSegment(segment_id=len(segments), text=text, start_seconds=start, end_seconds=end,
                timing=TimestampProvenance(timing_source=timing_source, alignment_method="caption_container", evidence_quality="coarse_segment")))
        return RawTranscriptDocument(segments=tuple(segments))

    @staticmethod
    def _parse_time(value: str) -> float:
        match = _TIMESTAMP.fullmatch(value.strip())
        if not match:
            raise ValueError(f"unsupported subtitle timestamp: {value}")
        h, m, s, ms = match.groups()
        frac = int(ms) / (10 ** len(ms))
        return int(h or 0) * 3600 + int(m) * 60 + int(s) + frac

    def normalize(self, document: RawTranscriptDocument, *, word_timings: Optional[Mapping[int, Sequence[WordTimingRecord]]] = None) -> NormalizedTranscriptResult:
        output: list[str] = []
        origins: list[_MappedChar] = []
        normalized_segments = []
        warnings_out = []
        non_speech = []
        previous_end = None
        previous_id = None
        segment_order: dict[int, int] = {}
        for raw in document.segments:
            if previous_end is not None and raw.start_seconds < previous_end:
                warnings_out.append(f"overlapping timestamps at segment {raw.segment_id}")
            if previous_id is not None and raw.segment_id < previous_id:
                warnings_out.append(f"out-of-order segment id {raw.segment_id}")
            previous_end, previous_id = raw.end_seconds, raw.segment_id
            text, charmap = _normalize_segment_text(raw.text, decode_entities=self.decode_caption_entities)
            if not text:
                continue
            if output:
                output.append(" ")
                origins.append(_MappedChar(None, None, None))
            start = len(origins)
            output.append(text)
            origins.extend(_MappedChar(raw.segment_id, c.raw_start, c.raw_end) for c in charmap)
            end = len(origins)
            flag = bool(_NON_SPEECH.match(text))
            if flag:
                non_speech.append(raw.segment_id)
            segment_order[raw.segment_id] = len(segment_order)
            normalized_segments.append(NormalizedSegment(raw.segment_id, raw.speaker, text, raw.start_seconds, raw.end_seconds, start, end, raw.timing, tuple((word_timings or {}).get(raw.segment_id, ())), flag))
        normalized_text = "".join(output)
        index = OffsetAlignmentIndex(document, normalized_text, origins, segment_order)
        sentences = self._make_sentences(document, normalized_text, normalized_segments, index)
        return NormalizedTranscriptResult(document, normalized_text, tuple(normalized_segments), tuple(sentences), index, tuple(warnings_out), tuple(non_speech))

    def ingest_and_normalize(
        self,
        raw_payload: dict | str | RawTranscriptDocument,
        source_format: Literal["youtube", "whisper", "srt", "vtt", "raw_document"],
        *,
        timing_source: TimingSource = "unknown",
    ) -> NormalizedTranscriptResult:
        word_timings: Optional[Mapping[int, Sequence[WordTimingRecord]]] = None
        if source_format == "raw_document":
            if not isinstance(raw_payload, RawTranscriptDocument):
                raise TypeError("raw_document source_format requires RawTranscriptDocument")
            document = raw_payload
        elif source_format == "youtube":
            if not isinstance(raw_payload, dict):
                raise TypeError("youtube source_format requires a mapping payload")
            document = self.from_youtube_captions(raw_payload)
        elif source_format == "whisper":
            if not isinstance(raw_payload, dict):
                raise TypeError("whisper source_format requires a mapping payload")
            document = self.from_whisper_transcript(raw_payload)
            word_timings = self.extract_whisper_words(raw_payload)
        elif source_format in ("srt", "vtt"):
            if not isinstance(raw_payload, str):
                raise TypeError(f"{source_format} source_format requires string content")
            document = self.from_srt_or_vtt(raw_payload, timing_source=timing_source)
        else:
            raise ValueError(f"unsupported source_format: {source_format}")
        return self.normalize(document, word_timings=word_timings)

    def _make_sentences(self, document, text, segments, index):
        if not text:
            return []
        cuts = []
        abbrev = re.compile(r"(?:\b(?:Dr|Mr|Mrs|Ms|Prof|U\.S|e\.g|i\.e)\.|\d+\.\d+)$", re.I)
        seg_by_char = {}
        for seg in segments:
            for i in range(seg.norm_start, seg.norm_end):
                seg_by_char[i] = seg
        for previous, current in zip(segments, segments[1:]):
            if current.speaker != previous.speaker or current.start_seconds - previous.end_seconds >= self.pause_sentence_gap_seconds:
                cuts.append(current.norm_start)
        for i, ch in enumerate(text):
            current = seg_by_char.get(i)
            if current and current.is_non_speech and i == current.norm_start:
                cuts.append(current.norm_start)
                cuts.append(current.norm_end)
            if ch in ".?!\u0964\u0965":
                if ch == "." and i + 1 < len(text) and text[i + 1] == ".":
                    continue
                if ch == "." and i > 0 and text[i - 1] == ".":
                    if i + 1 < len(text) and not text[i + 1].isspace():
                        continue
                prefix = text[max(0, i - 20):i + 1]
                decimal_dot = ch == "." and i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit()
                dotted_abbrev = ch == "." and i + 1 < len(text) and text[i + 1].isalpha() and not text[i + 1].isspace()
                if not decimal_dot and not dotted_abbrev and not abbrev.search(prefix.rstrip()):
                    cut = i + 1
                    while cut < len(text) and text[cut] in '\"\'\u201d\u2019)]':
                        cut += 1
                    cuts.append(cut)
        bounds = [0] + sorted(set(c for c in cuts if 0 < c < len(text))) + [len(text)]
        result = []
        for a, b in zip(bounds, bounds[1:]):
            while a < b and text[a].isspace(): a += 1
            while b > a and text[b - 1].isspace(): b -= 1
            if a == b: continue
            contributors = [seg for seg in segments if seg.norm_start < b and seg.norm_end > a]
            speakers = tuple(dict.fromkeys(seg.speaker for seg in contributors if seg.speaker))
            provs = [seg.timing_provenance for seg in contributors]
            quality_rank = {"high_subframe":0,"medium_word":1,"coarse_segment":2,"low_estimated":3,"unknown":4}
            weakest = max(provs, key=lambda p: quality_rank[p.evidence_quality]) if provs else TimestampProvenance()
            result.append(NormalizedSentence(len(result), text[a:b], a, b, tuple(index.map_normalized_span_to_raw(a,b)), speakers[0] if len(speakers)==1 else None, speakers,
                min((s.start_seconds for s in contributors), default=0.0), max((s.end_seconds for s in contributors), default=0.0), weakest))
        return result
