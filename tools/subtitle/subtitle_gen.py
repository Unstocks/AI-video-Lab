"""Offline transcript-to-subtitle tool for SRT, VTT, JSON, and ASS outputs."""

from __future__ import annotations

import json
import math
from html import escape
import time
import copy
import os
import re
from pathlib import Path
from typing import Any, Sequence

from lib.subtitle_styles import SubtitleStylePreset, get_subtitle_style, list_subtitle_styles

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolTier,
)


def rebase_segments_to_clip(
    segments: Sequence[dict[str, Any]], clip_start_seconds: float,
    clip_end_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Return transcript segments clipped and rebased onto a clip's zero PTS."""
    def finite(value: Any, field: str, *, minimum: float | None = None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        if minimum is not None and value < minimum:
            raise ValueError(f"{field} must be >= {minimum}")
        return float(value)

    clip_start = finite(clip_start_seconds, "clip_start_seconds", minimum=0)
    clip_end = None
    if clip_end_seconds is not None:
        clip_end = finite(clip_end_seconds, "clip_end_seconds", minimum=0)
        if clip_end <= clip_start:
            raise ValueError("clip_end_seconds must be greater than clip_start_seconds")
    clip_duration = clip_end - clip_start if clip_end is not None else None
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise TypeError("segments must be a sequence of objects")

    result: list[dict[str, Any]] = []
    for index, original in enumerate(segments):
        if not isinstance(original, dict):
            raise ValueError(f"segments[{index}] must be an object")
        segment = copy.deepcopy(original)
        words = segment.get("words") or []
        if words:
            word_intervals = []
            for word_index, word in enumerate(words):
                if not isinstance(word, dict):
                    raise ValueError(f"segments[{index}].words[{word_index}] must be an object")
                start = finite(word.get("start"), "word.start", minimum=0)
                end = finite(word.get("end"), "word.end", minimum=0)
                if end <= start:
                    raise ValueError("word.end must be greater than word.start")
                word_intervals.append((start, end, word))
            seg_start = min(row[0] for row in word_intervals)
            seg_end = max(row[1] for row in word_intervals)
        else:
            seg_start = finite(segment.get("start"), "segment.start", minimum=0)
            if "end" in segment:
                seg_end = finite(segment["end"], "segment.end", minimum=0)
            elif "duration" in segment:
                duration = finite(segment["duration"], "segment.duration", minimum=0)
                seg_end = seg_start + duration
            else:
                raise ValueError(f"segments[{index}] requires end or duration")
            if seg_end <= seg_start:
                continue
            word_intervals = []

        if seg_end <= clip_start or (clip_end is not None and seg_start >= clip_end):
            continue
        if word_intervals:
            rebased_words = []
            for start, end, word in word_intervals:
                if end <= clip_start or (clip_end is not None and start >= clip_end):
                    continue
                new_start = max(0.0, start - clip_start)
                new_end = end - clip_start
                if clip_duration is not None:
                    new_end = min(clip_duration, new_end)
                if new_end <= new_start:
                    continue
                word["start"], word["end"] = new_start, new_end
                rebased_words.append(word)
            if not rebased_words:
                continue
            segment["words"] = rebased_words
            segment["start"] = min(word["start"] for word in rebased_words)
            segment["end"] = max(word["end"] for word in rebased_words)
            segment["text"] = " ".join(
                str(word.get("word", word.get("text", ""))).strip()
                for word in rebased_words if str(word.get("word", word.get("text", ""))).strip()
            )
        else:
            new_start = max(0.0, seg_start - clip_start)
            new_end = seg_end - clip_start
            if clip_duration is not None:
                new_end = min(clip_duration, new_end)
            if new_end <= new_start:
                continue
            segment["start"], segment["end"] = new_start, new_end
            segment.pop("duration", None)
        result.append(segment)
    return result


class SubtitleGen(BaseTool):
    name = "subtitle_gen"
    version = "0.2.0"
    tier = ToolTier.CORE
    capability = "subtitle"
    provider = "openmontage"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = []  # pure Python
    install_instructions = "No external dependencies required."
    agent_skills = ["remotion-best-practices"]

    capabilities = ["generate_srt", "generate_vtt", "generate_caption_json", "generate_ass"]

    input_schema = {
        "type": "object",
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "description": "Transcript segments from transcriber (with words and timestamps)",
            },
            "format": {
                "type": "string",
                "enum": ["srt", "vtt", "json", "ass"],
                "default": "srt",
            },
            "clip_start_seconds": {"type": "number", "minimum": 0},
            "clip_end_seconds": {"type": "number", "exclusiveMinimum": 0},
            "play_res_x": {"type": "integer", "default": 1080},
            "play_res_y": {"type": "integer", "default": 1920},
            "font_name": {"type": "string", "default": "Noto Sans Devanagari"},
            "fonts_dir": {"type": "string"},
            "font_size": {"type": "integer", "default": 64},
            "margin_v": {"type": "integer", "default": 320},
            "margin_l": {"type": "integer", "default": 80},
            "margin_r": {"type": "integer", "default": 120},
            "output_path": {"type": "string"},
            "max_chars_per_line": {"type": "integer", "default": 42},
            "max_words_per_cue": {"type": "integer", "default": 8},
            "highlight_style": {
                "type": "string",
                "enum": ["none", "word_by_word", "karaoke"],
                "default": "none",
            },
            "corrections": {
                "type": "object",
                "description": (
                    "Dictionary of word corrections for common ASR misrecognitions. "
                    "Keys are the wrong word (case-insensitive), values are the "
                    "correct replacement. Applied before generating subtitles. "
                    "Example: {\"cloud\": \"Claude\", \"co-pilot\": \"Copilot\"}."
                ),
            },
            "style_preset": {
                "type": "string", "enum": list(list_subtitle_styles()),
                "description": "Optional offline ASS designer style preset.",
            },
            "split_ranges": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                },
                "description": "Optional [[start, end], ...] intervals where 2-speaker SPLIT layout is active (moves subtitles to center Style: Seam).",
            },
            "layout_ranges": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional .layout.json ranges array; 'split' entries automatically move subtitles to Style: Seam.",
            },
        },
    }

    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=10)
    idempotency_key_fields = [
        "segments", "format", "max_words_per_cue", "max_chars_per_line", "highlight_style",
        "clip_start_seconds", "clip_end_seconds", "play_res_x", "play_res_y", "font_name",
        "font_size", "margin_v", "margin_l", "margin_r", "corrections", "style_preset",
        "split_ranges", "layout_ranges",
    ]
    side_effects = ["writes subtitle file to output_path"]
    user_visible_verification = [
        "Play video with generated subtitles and verify timing",
    ]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        segments = inputs["segments"]
        fmt = inputs.get("format", "srt")
        max_words = inputs.get("max_words_per_cue", 8)
        max_chars = inputs.get("max_chars_per_line", 42)
        highlight_style = inputs.get("highlight_style", "none")
        output_path = inputs.get("output_path")
        corrections = inputs.get("corrections")
        warnings: list[str] = []
        style_preset_name = inputs.get("style_preset")
        try:
            preset = get_subtitle_style(style_preset_name) if style_preset_name is not None else None
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))
        if preset is not None:
            max_words = inputs.get("max_words_per_cue", preset.max_words_per_cue)
            max_chars = inputs.get("max_chars_per_line", preset.max_chars_per_line)

        start = time.time()

        # Apply word corrections if provided
        if corrections:
            segments = self._apply_corrections(segments, corrections)

        if ("clip_start_seconds" in inputs or "clip_end_seconds" in inputs
                or any("duration" in segment for segment in segments)):
            segments = rebase_segments_to_clip(
                segments, inputs.get("clip_start_seconds", 0.0), inputs.get("clip_end_seconds"))

        has_word_timings = any(bool(segment.get("words")) for segment in segments)
        effective_highlight_style = highlight_style
        if highlight_style in ("word_by_word", "karaoke") and not has_word_timings:
            effective_highlight_style = "none"
            warnings.append("highlight_style downgraded to 'none': word-level timestamps unavailable")

        # Build cues from word-level timestamps
        cues = self._build_cues(segments, max_words, max_chars)
        font_name = inputs.get("font_name", preset.font_name if preset else "Noto Sans Devanagari")
        font_size = inputs.get("font_size", preset.font_size if preset else 64)
        margin_l = inputs.get("margin_l", preset.margin_l if preset else 80)
        margin_r = inputs.get("margin_r", preset.margin_r if preset else 120)
        play_res_x = inputs.get("play_res_x", 1080)
        longest = max((len(line) for cue in cues for line in str(cue.get("text", "")).splitlines()), default=0)
        if longest * font_size * 0.58 > play_res_x - margin_l - margin_r:
            warnings.append("estimated subtitle line width exceeds the available play width; inspect for overflow")
        if fmt == "ass":
            font_dirs = []
            if inputs.get("fonts_dir"):
                font_dirs.append(Path(inputs["fonts_dir"]).expanduser())
            if os.name == "nt":
                font_dirs.extend([Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"])
            else:
                font_dirs.extend([Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"])
            inspectable = [directory for directory in font_dirs if directory.is_dir()]
            normalized_family = re.sub(r"[^a-z0-9]", "", font_name.casefold())
            found = any(normalized_family in re.sub(r"[^a-z0-9]", "", font_file.stem.casefold())
                        for directory in inspectable for font_file in directory.rglob("*")
                        if font_file.suffix.casefold() in {".ttf", ".otf", ".ttc"})
            if inspectable and not found:
                warnings.append(f"font '{font_name}' was not found in configured or inspectable system font directories")

        if fmt == "srt":
            content = self._render_srt(cues, effective_highlight_style)
            ext = ".srt"
        elif fmt == "vtt":
            content = self._render_vtt(cues, effective_highlight_style)
            ext = ".vtt"
        elif fmt == "json":
            content = json.dumps({"cues": cues, "highlight_style": effective_highlight_style}, indent=2, ensure_ascii=False)
            ext = ".caption.json"
        elif fmt == "ass":
            active_split_ranges: list[tuple[float, float]] = []
            for pair in inputs.get("split_ranges") or []:
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    s_r, e_r = float(pair[0]), float(pair[1])
                    if e_r > s_r:
                        active_split_ranges.append((s_r, e_r))
            if inputs.get("layout_ranges"):
                from lib.layout_ranges import split_ranges as _extract_split_ranges
                active_split_ranges.extend(_extract_split_ranges(inputs["layout_ranges"]))
            content = self._render_ass(
                cues, effective_highlight_style,
                play_res_x=inputs.get("play_res_x", 1080), play_res_y=inputs.get("play_res_y", 1920),
                font_name=font_name,
                font_size=font_size,
                margin_v=inputs.get("margin_v", preset.margin_v if preset else 320),
                margin_l=inputs.get("margin_l", preset.margin_l if preset else 80),
                margin_r=inputs.get("margin_r", preset.margin_r if preset else 120),
                preset=preset,
                split_ranges=active_split_ranges or None,
            )
            ext = ".ass"
        else:
            return ToolResult(success=False, error=f"Unknown format: {fmt}")

        if output_path is None:
            output_path = f"subtitles{ext}"
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8", newline="\n")

        elapsed = time.time() - start

        data = {
            "format": fmt,
            "cue_count": len(cues),
            "output": str(out),
            "warnings": warnings,
            "effective_highlight_style": effective_highlight_style,
        }
        if style_preset_name is not None:
            data["style_preset"] = style_preset_name
        return ToolResult(
            success=True,
            data=data,
            artifacts=[str(out)],
            duration_seconds=round(elapsed, 2),
        )

    @staticmethod
    def _apply_corrections(
        segments: list[dict], corrections: dict[str, str]
    ) -> list[dict]:
        """Apply word-level corrections to transcript segments.

        Handles case-insensitive matching and preserves punctuation.
        """
        import copy

        corr = {k.lower(): v for k, v in corrections.items()}
        result = copy.deepcopy(segments)

        for seg in result:
            words = seg.get("words", [])
            for w in words:
                raw = w.get("word", "").strip()
                # Strip punctuation for lookup, preserve it
                stripped = raw.lower().rstrip(".,!?;:'\"")
                if stripped in corr:
                    trailing = raw[len(stripped):]
                    w["word"] = corr[stripped] + trailing
            # Also fix segment-level text
            if "text" in seg and words:
                seg["text"] = " ".join(w["word"] for w in words)
            elif "text" in seg:
                for wrong, right in corr.items():
                    import re as _re
                    seg["text"] = _re.sub(
                        r"\b" + _re.escape(wrong) + r"\b",
                        lambda match, replacement=right: replacement,
                        seg["text"],
                        flags=_re.IGNORECASE,
                    )

        return result

    @staticmethod
    def merge_continuation_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge Whisper continuation fragments onto their base word and extend ``end``.

        Handles both:
        - Raw Whisper streams that mark word boundaries with leading spaces
          (e.g. ``" anti"`` + ``"-hero"``, ``" $20"`` + ``".50"``, ``" don"`` + ``"'t"``).
        - Pre-stripped word streams containing explicit continuation tokens
          starting with ``-``, ``'``, ``’``, ``.``, or standalone punctuation.
        """
        if not words:
            return []

        uses_leading_space = any(
            isinstance(w.get("word"), str) and len(w["word"]) > 1 and w["word"][0].isspace()
            for w in words[1:]
        )

        merged: list[dict[str, Any]] = []
        for item in words:
            raw = str(item.get("word", ""))
            stripped = raw.strip()
            if not stripped:
                continue

            is_continuation = False
            if merged:
                if uses_leading_space and not raw[0].isspace():
                    is_continuation = True
                elif re.fullmatch(r"['\u2019](?:s|t|re|ve|ll|d|m)\b", stripped, re.IGNORECASE):
                    # Contractions / possessives in stripped streams ('s, 't, 're, 've, 'll, 'd, 'm)
                    is_continuation = True
                elif re.fullmatch(r"-\w+", stripped) and not re.fullmatch(r"-\d+(?:\.\d+)?", stripped):
                    # Hyphenated word suffix (-hero) while preserving negative numbers (-5)
                    is_continuation = True
                elif re.fullmatch(r"\.\d+", stripped) and re.search(r"\d$", merged[-1]["word"]):
                    # Decimal tail (.50) attached to a preceding number ($20 -> $20.50), not .NET
                    is_continuation = True
                elif all(ch in ".,!?;:%)]}" for ch in stripped) and not stripped.startswith("..."):
                    is_continuation = True

            if is_continuation:
                prev = merged[-1]
                prev["word"] = f"{prev['word']}{stripped}"
                prev["end"] = max(float(prev["end"]), float(item["end"]))
            else:
                merged.append({
                    **item,
                    "word": stripped,
                    "start": float(item["start"]),
                    "end": float(item["end"]),
                })
        return merged

    def _build_cues(
        self, segments: list[dict], max_words: int, max_chars: int
    ) -> list[dict]:
        """Group words into display cues respecting max_words and max_chars."""
        # Collect all words with timestamps
        all_words = []
        for seg in segments:
            words = seg.get("words", [])
            if words:
                all_words.extend(self.merge_continuation_words(list(words)))
            elif "text" in seg:
                # Fallback: segment-level only (no word timestamps)
                all_words.append({
                    "word": seg["text"],
                    "start": seg["start"],
                    "end": seg["end"],
                })

        if not all_words:
            return []

        cues = []
        buf: list[dict] = []
        buf_text = ""

        for w in all_words:
            word_text = w["word"].strip()
            candidate = f"{buf_text} {word_text}".strip() if buf_text else word_text

            if buf and (len(buf) >= max_words or len(candidate) > max_chars):
                cues.append({
                    "index": len(cues) + 1,
                    "start": buf[0]["start"],
                    "end": buf[-1]["end"],
                    "text": buf_text,
                    "words": [
                        {"word": b["word"].strip(), "start": b["start"], "end": b["end"]}
                        for b in buf
                    ],
                })
                buf = []
                buf_text = ""

            buf.append(w)
            buf_text = f"{buf_text} {word_text}".strip() if buf_text else word_text

        # Flush remaining
        if buf:
            cues.append({
                "index": len(cues) + 1,
                "start": buf[0]["start"],
                "end": buf[-1]["end"],
                "text": buf_text,
                "words": [
                    {"word": b["word"].strip(), "start": b["start"], "end": b["end"]}
                    for b in buf
                ],
            })

        return cues

    def _render_srt(self, cues: list[dict], highlight_style: str = "none") -> str:
        lines = []
        if highlight_style == "word_by_word":
            # Emit one cue per word for word-by-word reveal
            idx = 1
            for cue in cues:
                for word_info in cue.get("words", []):
                    lines.append(str(idx))
                    lines.append(
                        f"{self._ts_srt(word_info['start'])} --> {self._ts_srt(word_info['end'])}"
                    )
                    lines.append(word_info["word"])
                    lines.append("")
                    idx += 1
        elif highlight_style == "karaoke":
            # Show full cue text but bold the active word using SRT HTML tags
            for cue in cues:
                words = cue.get("words", [])
                if not words:
                    lines.append(str(cue["index"]))
                    lines.append(f"{self._ts_srt(cue['start'])} --> {self._ts_srt(cue['end'])}")
                    lines.append(cue["text"])
                    lines.append("")
                    continue
                for wi, word_info in enumerate(words):
                    lines.append(str(cue["index"] * 100 + wi))
                    lines.append(
                        f"{self._ts_srt(word_info['start'])} --> {self._ts_srt(word_info['end'])}"
                    )
                    parts = []
                    for wj, w in enumerate(words):
                        if wj == wi:
                            parts.append(f"<b>{w['word']}</b>")
                        else:
                            parts.append(w["word"])
                    lines.append(" ".join(parts))
                    lines.append("")
        else:
            for cue in cues:
                lines.append(str(cue["index"]))
                lines.append(f"{self._ts_srt(cue['start'])} --> {self._ts_srt(cue['end'])}")
                lines.append(cue["text"])
                lines.append("")
        return "\n".join(lines)

    def _render_vtt(self, cues: list[dict], highlight_style: str = "none") -> str:
        lines = ["WEBVTT", ""]
        if highlight_style == "word_by_word":
            for cue in cues:
                for word_info in cue.get("words", []):
                    lines.append(
                        f"{self._ts_vtt(word_info['start'])} --> {self._ts_vtt(word_info['end'])}"
                    )
                    lines.append(escape(word_info["word"], quote=False))
                    lines.append("")
        elif highlight_style == "karaoke":
            for cue in cues:
                words = cue.get("words", [])
                if not words:
                    lines.append(f"{self._ts_vtt(cue['start'])} --> {self._ts_vtt(cue['end'])}")
                    lines.append(escape(cue["text"], quote=False))
                    lines.append("")
                    continue
                for wi, word_info in enumerate(words):
                    lines.append(
                        f"{self._ts_vtt(word_info['start'])} --> {self._ts_vtt(word_info['end'])}"
                    )
                    parts = []
                    for wj, w in enumerate(words):
                        if wj == wi:
                            parts.append(f"<b>{escape(w['word'], quote=False)}</b>")
                        else:
                            parts.append(escape(w["word"], quote=False))
                    lines.append(" ".join(parts))
                    lines.append("")
        else:
            for cue in cues:
                lines.append(f"{self._ts_vtt(cue['start'])} --> {self._ts_vtt(cue['end'])}")
                lines.append(escape(cue["text"], quote=False))
                lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _ts_ass(seconds: float) -> str:
        """ASS timestamp format H:MM:SS.cc (centiseconds, rounded with carry)."""
        total_cs = int(round(max(0.0, seconds) * 100))
        hours, remaining = divmod(total_cs, 360_000)
        minutes, remaining = divmod(remaining, 6_000)
        whole_seconds, centiseconds = divmod(remaining, 100)
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"

    @staticmethod
    def _escape_ass_text(value: str) -> str:
        return (str(value).replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")
                .replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N"))

    def _render_ass(
        self, cues: list[dict], highlight_style: str = "none", *,
        play_res_x: int = 1080, play_res_y: int = 1920,
        font_name: str = "Noto Sans Devanagari", font_size: int = 64,
        margin_v: int = 320, margin_l: int = 80, margin_r: int = 120,
        preset: SubtitleStylePreset | None = None,
        split_ranges: list[tuple[float, float]] | None = None,
    ) -> str:
        values = (play_res_x, play_res_y, font_size, margin_v, margin_l, margin_r)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("ASS resolution, font size, and margins must be integers")
        if play_res_x <= 0 or play_res_y <= 0 or font_size <= 0 or min(margin_v, margin_l, margin_r) < 0:
            raise ValueError("ASS resolution/font size must be positive and margins nonnegative")
        if highlight_style not in ("none", "word_by_word", "karaoke"):
            raise ValueError("unsupported ASS highlight_style")
        safe_font = str(font_name).replace(",", " ").replace("\n", " ").replace("\r", " ")
        active_split_ranges = [
            (float(s), float(e)) for s, e in (split_ranges or []) if float(e) > float(s)
        ]

        def _style_row(name: str, alignment: int, v_margin: int) -> str:
            if preset is None:
                return (
                    f"Style: {name},{safe_font},{font_size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,"
                    f"-1,0,0,0,100,100,0,0,1,4,2,{alignment},{margin_l},{margin_r},{v_margin},1"
                )
            return (
                f"Style: {name},{safe_font},{font_size},{preset.primary_color},{preset.secondary_color},"
                f"{preset.outline_color},{preset.back_color},{-1 if preset.bold else 0},{-1 if preset.italic else 0},"
                f"0,0,100,100,0,0,{preset.border_style},{preset.outline:g},{preset.shadow:g},"
                f"{alignment},{margin_l},{margin_r},{v_margin},1"
            )

        default_align = 2 if preset is None else preset.alignment
        lines = [
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {play_res_x}",
            f"PlayResY: {play_res_y}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            _style_row("Default", default_align, margin_v),
        ]
        if active_split_ranges:
            # Dedicated Style: Seam (Alignment=5 middle-center, MarginV=0) survives {\r} active-word resets!
            lines.append(_style_row("Seam", 5, 0))
        lines.extend([
            "", "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ])

        def dialogue(start: float, end: float, text: str) -> str:
            if end <= start:
                return ""
            mid = (float(start) + float(end)) / 2.0
            style_name = (
                "Seam"
                if active_split_ranges and any(s <= mid < e for s, e in active_split_ranges)
                else "Default"
            )
            return f"Dialogue: 0,{self._ts_ass(start)},{self._ts_ass(end)},{style_name},,0,0,0,,{text}"

        def display(value: Any) -> str:
            raw = str(value)
            if preset is not None and preset.uppercase:
                raw = raw.upper()
            return self._escape_ass_text(raw)

        def with_glow(text: str) -> str:
            if preset is not None and preset.glow_blur > 0:
                return f"{{\\blur{preset.glow_blur:g}}}{text}"
            return text

        for cue in cues:
            words = cue.get("words") or []
            if highlight_style == "word_by_word" and words:
                for word in words:
                    text = with_glow(display(word.get("word", "")))
                    row = dialogue(word["start"], word["end"], text)
                    if row:
                        lines.append(row)
                continue
            if highlight_style == "karaoke" and words:
                if preset is not None and preset.active_word_mode == "none":
                    row = dialogue(cue["start"], cue["end"], with_glow(display(cue.get("text", ""))))
                    if row:
                        lines.append(row)
                    continue
                if preset is not None and preset.active_word_mode in ("active_pop", "active_color"):
                    active_bgr = f"&H{preset.secondary_color[4:]}"
                    reset_tag = f"{{\\r\\blur{preset.glow_blur:g}}}" if preset.glow_blur > 0 else "{\\r}"
                    for active_index, active_word in enumerate(words):
                        pieces = []
                        for word_index, word in enumerate(words):
                            word_text = display(word.get("word", ""))
                            if word_index == active_index:
                                tag = f"{{\\c{active_bgr}&"
                                if preset.active_word_mode == "active_pop":
                                    tag += (f"\\t(0,80,\\fscx{preset.pop_scale_percent}\\fscy{preset.pop_scale_percent})"
                                            "\\t(80,180,\\fscx100\\fscy100)")
                                if preset.glow_blur > 0:
                                    tag += f"\\blur{preset.glow_blur:g}"
                                word_text = f"{tag}}}{word_text}{reset_tag}"
                            pieces.append(word_text)
                        row = dialogue(active_word["start"], active_word["end"], with_glow(" ".join(pieces)))
                        if row:
                            lines.append(row)
                    continue
                pieces = []
                for word in words:
                    word_text = display(word.get("word", ""))
                    duration_cs = max(0, int(round((word["end"] - word["start"]) * 100)))
                    pieces.append(f"{{\\kf{duration_cs}}}{word_text}")
                text = with_glow(" ".join(pieces))
            else:
                text = with_glow(display(cue.get("text", "")))
            row = dialogue(cue["start"], cue["end"], text)
            if row:
                lines.append(row)
        return "\n".join(lines) + "\n"

    @staticmethod
    def _hmsms(seconds: float) -> tuple[int, int, int, int]:
        """Decompose seconds into (h, m, s, ms), rounding to whole ms first.

        Rounding to total milliseconds before splitting the fields lets the
        carry propagate: 0.9995s+ must become the next second (…,000), not a
        malformed 4-digit …,1000 with the seconds field left unincremented.
        """
        total_ms = int(round(max(0.0, seconds) * 1000))
        h, rem = divmod(total_ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1_000)
        return h, m, s, ms

    @classmethod
    def _ts_srt(cls, seconds: float) -> str:
        """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
        h, m, s, ms = cls._hmsms(seconds)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    @classmethod
    def _ts_vtt(cls, seconds: float) -> str:
        """Format seconds as VTT timestamp: HH:MM:SS.mmm"""
        h, m, s, ms = cls._hmsms(seconds)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
