"""Zero-tolerance verification that proposed spoken hooks exist verbatim."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from lib.models.clip_plan import SpokenHookEvidence
from lib.models.transcript import RawTranscriptDocument, RawTranscriptSegment, SourceSpan
from lib.transcript_normalizer import NormalizedTranscriptResult, TranscriptNormalizer


@dataclass(frozen=True)
class HookValidationResult:
    valid: bool
    evidence: Optional[SpokenHookEvidence]
    failure_reason: Optional[str] = None
    matched_norm_span: Optional[tuple[int, int]] = None
    matched_start_seconds: Optional[float] = None
    matched_end_seconds: Optional[float] = None
    warnings: tuple[str, ...] = ()


def _canonical(text: str) -> str:
    if not isinstance(text, str):
        return ""
    document = RawTranscriptDocument(segments=(RawTranscriptSegment(
        segment_id=0, text=text, start_seconds=0.0, end_seconds=0.0),))
    return TranscriptNormalizer().normalize(document).normalized_text


def _word_boundary(text: str, start: int, end: int) -> bool:
    def boundary(index: int) -> bool:
        if index < 0 or index >= len(text):
            return True
        char = text[index]
        return char.isspace() or unicodedata.category(char).startswith("P")
    return boundary(start - 1) and boundary(end)


def _failure(reason: str, *, warnings: tuple[str, ...] = ()) -> HookValidationResult:
    return HookValidationResult(False, None, reason, warnings=warnings)


def _validate_spans(
    spans: Sequence[SourceSpan], normalized: NormalizedTranscriptResult, *,
    expected_text: str, expected_speaker: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    if not spans:
        return None, "hook source spans are empty"
    document = normalized.raw_document
    segments = {segment.segment_id: segment for segment in document.segments}
    non_speech = set(normalized.non_speech_segment_ids)
    order = normalized.alignment_index._segment_order
    previous: Optional[SourceSpan] = None
    speakers = set()
    for span in spans:
        if span.transcript_revision_id != document.transcript_revision_id:
            return None, "transcript revision mismatch"
        if span.gap_before is not None:
            return None, "hook spans contain a transcript gap"
        segment = segments.get(span.segment_id)
        if segment is None or not (0 <= span.char_start < span.char_end <= len(segment.text)):
            return None, "hook source span is out of bounds or empty"
        if span.segment_id in non_speech:
            return None, "hook includes a non-speech segment"
        speakers.add(segment.speaker)
        if previous is not None:
            if order.get(span.segment_id, -1) < order.get(previous.segment_id, -1):
                return None, "hook source spans are not ordered"
            if span.segment_id == previous.segment_id:
                if span.char_start != previous.char_end:
                    return None, "hook source spans are not contiguous"
            elif order.get(span.segment_id, -1) != order.get(previous.segment_id, -1) + 1:
                return None, "hook skips an intervening non-empty transcript segment"
        previous = span
    if len(speakers) > 1:
        return None, "hook spans multiple speakers"
    speaker = next(iter(speakers))
    if expected_speaker is not None and speaker != expected_speaker:
        return None, "hook speaker does not match expected_speaker"
    slices = normalized.extract_raw_slices(spans)
    raw_parts: list[str] = []
    previous_segment_id: Optional[int] = None
    for span, raw_slice in zip(spans, slices):
        if previous_segment_id is not None and span.segment_id != previous_segment_id:
            raw_parts.append(" ")
        raw_parts.append(raw_slice)
        previous_segment_id = span.segment_id
    raw_text = "".join(raw_parts)
    actual = _canonical(raw_text)
    if actual != expected_text and actual.casefold() != expected_text.casefold():
        return None, "hook text does not exactly match the supplied source spans"
    return speaker, None


def validate_hook_provenance(
    proposed_hook_text: str,
    normalized: NormalizedTranscriptResult,
    *,
    clip_start_seconds: Optional[float] = None,
    clip_end_seconds: Optional[float] = None,
    source_spans: Optional[Sequence[SourceSpan]] = None,
    expected_speaker: Optional[str] = None,
    opening_window_seconds: Optional[float] = None,
    require_in_opening_window: bool = False,
) -> HookValidationResult:
    if not isinstance(proposed_hook_text, str) or not proposed_hook_text.strip():
        return _failure("proposed hook is empty")
    for value, name in ((clip_start_seconds, "clip_start_seconds"),
                        (clip_end_seconds, "clip_end_seconds"),
                        (opening_window_seconds, "opening_window_seconds")):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            return _failure(f"{name} must be a finite number")
        if value is not None and value < 0:
            return _failure(f"{name} must be nonnegative")
    if clip_start_seconds is not None and clip_end_seconds is not None and clip_end_seconds <= clip_start_seconds:
        return _failure("clip_end_seconds must be greater than clip_start_seconds")
    canonical = _canonical(proposed_hook_text)
    if not canonical:
        return _failure("proposed hook normalizes to empty text")

    warnings: list[str] = []
    if source_spans is not None:
        speaker, error = _validate_spans(source_spans, normalized, expected_text=canonical,
                                         expected_speaker=expected_speaker)
        if error:
            return _failure(error)
        spans = tuple(source_spans)
        starts = [segment.start_seconds for segment in normalized.raw_document.segments
                  if segment.segment_id == spans[0].segment_id]
        ends = [segment.end_seconds for segment in normalized.raw_document.segments
                if segment.segment_id == spans[-1].segment_id]
        matched_start = starts[0] if starts else None
        matched_end = ends[0] if ends else None
        try:
            evidence = SpokenHookEvidence(text=proposed_hook_text.strip(), speaker=speaker, source_spans=spans)
        except Exception as exc:
            return _failure(f"invalid spoken hook evidence: {exc}")
        matched_span = normalized.map_raw_span_to_normalized(spans[0].segment_id,
            spans[0].char_start, spans[0].char_end)
        matched_span_end = normalized.map_raw_span_to_normalized(spans[-1].segment_id,
            spans[-1].char_start, spans[-1].char_end)
        norm_span = (matched_span[0], matched_span_end[1]) if matched_span and matched_span_end else None
    else:
        text = normalized.normalized_text
        allowed_ids = None
        if clip_start_seconds is not None or clip_end_seconds is not None:
            if clip_start_seconds is None or clip_end_seconds is None:
                return _failure("clip_start_seconds and clip_end_seconds must be provided together")
            allowed_ids = {segment.segment_id for segment in normalized.segments
                           if segment.end_seconds >= clip_start_seconds and segment.start_seconds <= clip_end_seconds}
        match = None
        spans = ()
        match_failure: Optional[str] = None
        # Preserve exact text.find() preference, then allow case-insensitive
        # verbatim matches. Regex offsets remain original-string coordinates.
        def exact_matches():
            cursor = 0
            while True:
                found = text.find(canonical, cursor)
                if found < 0:
                    return
                yield found, found + len(canonical)
                cursor = found + 1

        for candidates in (
            exact_matches(),
            (m.span() for m in re.finditer(re.escape(canonical), text, flags=re.IGNORECASE)),
        ):
            for found, end_index in candidates:
                if not _word_boundary(text, found, end_index):
                    continue
                candidate_spans = normalized.map_normalized_span_to_raw(found, end_index)
                if not candidate_spans:
                    continue
                if allowed_ids is not None and any(span.segment_id not in allowed_ids for span in candidate_spans):
                    continue
                speaker, error = _validate_spans(candidate_spans, normalized, expected_text=canonical,
                                                 expected_speaker=expected_speaker)
                if error:
                    match_failure = match_failure or error
                    continue
                match = (found, end_index, speaker)
                spans = tuple(candidate_spans)
                break
            if match is not None:
                break
        if match is None:
            return _failure(match_failure or "no exact single-speaker hook match found within the permitted transcript window")
        norm_start, norm_end, speaker = match
        source_segments = {segment.segment_id: segment for segment in normalized.raw_document.segments}
        matched_start = source_segments[spans[0].segment_id].start_seconds
        matched_end = source_segments[spans[-1].segment_id].end_seconds
        norm_span = (norm_start, norm_end)
        try:
            evidence = SpokenHookEvidence(text=proposed_hook_text.strip(), speaker=speaker, source_spans=spans)
        except Exception as exc:
            return _failure(f"invalid spoken hook evidence: {exc}")

    if clip_start_seconds is not None and opening_window_seconds is not None and matched_start is not None:
        if matched_start > clip_start_seconds + opening_window_seconds:
            warnings.append("hook is outside the configured opening window")
            if require_in_opening_window:
                return _failure("hook is outside the required opening window", warnings=tuple(warnings))
    return HookValidationResult(True, evidence, matched_norm_span=norm_span,
                                matched_start_seconds=matched_start,
                                matched_end_seconds=matched_end, warnings=tuple(warnings))
