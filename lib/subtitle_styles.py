"""Offline designer subtitle presets and ASS color helpers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping


@dataclass(frozen=True)
class SubtitleStylePreset:
    name: str
    display_name: str
    description: str
    font_name: str
    font_size: int
    primary_color: str
    secondary_color: str
    outline_color: str
    back_color: str
    bold: bool = True
    italic: bool = False
    border_style: Literal[1, 3] = 1
    outline: float = 4.0
    shadow: float = 2.0
    alignment: int = 2
    margin_l: int = 80
    margin_r: int = 120
    margin_v: int = 320
    max_words_per_cue: int = 5
    max_chars_per_line: int = 28
    uppercase: bool = False
    active_word_mode: Literal["karaoke_fill", "active_pop", "active_color", "none"] = "active_color"
    pop_scale_percent: int = 116
    glow_blur: float = 0.0
    recommended_for: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("name", "display_name", "description", "font_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("primary_color", "secondary_color", "outline_color", "back_color"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"&H[0-9A-Fa-f]{8}", value):
                raise ValueError(f"{name} must be an ASS &HAABBGGRR color")
            object.__setattr__(self, name, value.upper())
        for name in ("font_size", "alignment", "border_style", "margin_l", "margin_r", "margin_v",
                     "max_words_per_cue", "max_chars_per_line", "pop_scale_percent"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if self.alignment not in range(1, 10):
            raise ValueError("alignment must be between 1 and 9")
        if self.border_style not in (1, 3):
            raise ValueError("border_style must be 1 or 3")
        if min(self.margin_l, self.margin_r, self.margin_v) < 0:
            raise ValueError("margins must be nonnegative")
        if self.max_words_per_cue <= 0 or self.max_chars_per_line <= 0:
            raise ValueError("cue word and character limits must be positive")
        if self.pop_scale_percent < 100:
            raise ValueError("pop_scale_percent must be >= 100")
        if self.active_word_mode not in ("karaoke_fill", "active_pop", "active_color", "none"):
            raise ValueError("unsupported active_word_mode")
        for name in ("outline", "shadow", "glow_blur"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite nonnegative number")
        if not isinstance(self.bold, bool) or not isinstance(self.italic, bool) or not isinstance(self.uppercase, bool):
            raise ValueError("bold, italic, and uppercase must be booleans")
        if not isinstance(self.recommended_for, tuple) or any(not isinstance(item, str) for item in self.recommended_for):
            raise ValueError("recommended_for must be a tuple of strings")


def hex_to_ass_color(hex_rgb: str, *, alpha: int = 0) -> str:
    """Convert ``#RRGGBB`` to ASS ``&HAABBGGRR`` (ASS stores BGR order)."""
    if not isinstance(hex_rgb, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", hex_rgb):
        raise ValueError("hex_rgb must be exactly #RRGGBB")
    if isinstance(alpha, bool) or not isinstance(alpha, int) or not 0 <= alpha <= 255:
        raise ValueError("alpha must be an integer from 0 to 255")
    red, green, blue = (hex_rgb[index:index + 2].upper() for index in (1, 3, 5))
    return f"&H{alpha:02X}{blue}{green}{red}"


def _preset(name: str, display_name: str, description: str, font_name: str, size: int,
            primary: str, active: str, outline_hex: str, back: str, *,
            outline_alpha: int = 0, **kwargs: object) -> SubtitleStylePreset:
    return SubtitleStylePreset(
        name=name, display_name=display_name, description=description, font_name=font_name,
        font_size=size, primary_color=hex_to_ass_color(primary), secondary_color=hex_to_ass_color(active),
        outline_color=hex_to_ass_color(outline_hex, alpha=outline_alpha), back_color=back, **kwargs,
    )


SUBTITLE_STYLE_PRESETS: Mapping[str, SubtitleStylePreset] = MappingProxyType({
    "hormozi_pop": _preset(
        "hormozi_pop", "Hormozi Pop", "Bold uppercase, word-by-word impact captions.",
        "Montserrat", 76, "#FFFFFF", "#FFE600", "#000000", hex_to_ass_color("#000000", alpha=0),
        outline=6.0, shadow=3.0, uppercase=True, active_word_mode="active_pop", pop_scale_percent=118,
        max_words_per_cue=3, max_chars_per_line=22, margin_v=340,
        recommended_for=("comedy_banter", "solo_monologue", "guest_qa"),
    ),
    "neon_glow": _preset(
        "neon_glow", "Neon Glow", "Cyan active words with a soft magenta glow.",
        "Outfit", 70, "#FFFFFF", "#00FFFF", "#E600FF", hex_to_ass_color("#000000"),
        outline=4.5, shadow=0.0, uppercase=True, active_word_mode="active_pop", pop_scale_percent=112,
        glow_blur=3.5, max_words_per_cue=4,
        recommended_for=("technical_deep_dive", "debate", "comedy_banter"),
    ),
    "pill_highlight": _preset(
        "pill_highlight", "Pill Highlight", "Gold active word over an opaque dark box.",
        "Poppins", 64, "#FFFFFF", "#FFD700", "#000000", hex_to_ass_color("#000000", alpha=90),
        outline_alpha=64, border_style=3, outline=8.0, shadow=0.0, uppercase=False,
        active_word_mode="active_color", max_words_per_cue=5,
        recommended_for=("guest_qa", "technical_deep_dive", "multilingual_hinglish"),
    ),
    "editorial_serif": _preset(
        "editorial_serif", "Editorial Serif", "Warm serif captions with restrained emphasis.",
        "Playfair Display", 60, "#FAF7F2", "#F0B860", "#171512", hex_to_ass_color("#000000"),
        bold=False, italic=False, outline=2.0, shadow=1.5, active_word_mode="active_color",
        recommended_for=("personal_narrative", "solo_monologue", "debate"),
    ),
    "hinglish_impact": _preset(
        "hinglish_impact", "Hinglish Impact", "Devanagari-safe impact captions; never uppercase the script.",
        "Noto Sans Devanagari", 70, "#FFFFFF", "#FFB800", "#000000", hex_to_ass_color("#000000"),
        uppercase=False, outline=5.0, shadow=2.5, active_word_mode="active_pop", pop_scale_percent=114,
        margin_v=340, max_words_per_cue=4,
        recommended_for=("multilingual_hinglish", "guest_qa", "personal_narrative"),
    ),
    "viral_bounce": _preset(
        "viral_bounce", "Viral Bounce", "Oversized playful uppercase captions with lime emphasis.",
        "Bangers", 82, "#FFFFFF", "#39FF14", "#000000", hex_to_ass_color("#000000"),
        uppercase=True, outline=6.5, shadow=3.0, active_word_mode="active_pop", pop_scale_percent=124,
        max_words_per_cue=3, max_chars_per_line=20,
        recommended_for=("comedy_banter", "solo_monologue", "guest_qa"),
    ),
    "documentary_clean": _preset(
        "documentary_clean", "Documentary Clean", "Airy captions over a translucent dark band.",
        "Inter", 56, "#FFFFFF", "#7DD3FC", "#000000", hex_to_ass_color("#000000", alpha=128),
        outline_alpha=128, bold=False, border_style=3, outline=6.0, shadow=0.0, uppercase=False,
        active_word_mode="karaoke_fill", margin_v=300, max_words_per_cue=7, max_chars_per_line=38,
        recommended_for=("technical_deep_dive", "personal_narrative", "debate"),
    ),
    "minimal_mono": _preset(
        "minimal_mono", "Minimal Mono", "Compact monospaced captions with emerald karaoke fill.",
        "JetBrains Mono", 54, "#FFFFFF", "#4ADE80", "#000000", hex_to_ass_color("#000000"),
        bold=True, uppercase=False, outline=3.0, shadow=1.0, active_word_mode="karaoke_fill",
        max_words_per_cue=5, max_chars_per_line=32,
        recommended_for=("technical_deep_dive", "debate", "solo_monologue"),
    ),
})


def get_subtitle_style(name: str) -> SubtitleStylePreset:
    if not isinstance(name, str) or name not in SUBTITLE_STYLE_PRESETS:
        names = ", ".join(sorted(SUBTITLE_STYLE_PRESETS))
        raise ValueError(f"unknown subtitle style {name!r}; available presets: {names}")
    return SUBTITLE_STYLE_PRESETS[name]


def list_subtitle_styles() -> tuple[str, ...]:
    return tuple(sorted(SUBTITLE_STYLE_PRESETS))
