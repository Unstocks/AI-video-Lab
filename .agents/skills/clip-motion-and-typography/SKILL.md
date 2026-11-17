---
name: clip-motion-and-typography
description: Choose offline caption presets, safe multilingual typography, and purposeful motion graphics for short-form clips.
---

# Clip Motion and Typography

Use this skill when styling ASS captions, planning short-form motion graphics, or documenting a HyperFrames composition. Wave 6A ships offline FFmpeg subtitle presets. HyperFrames and background removal below are reference patterns for a later renderer wave; do not invoke `npx` as part of the current offline subtitle workflow.

## Offline ASS Designer Presets

Select `style_preset` in `SubtitleGen` or `VerticalRenderConfig`. Keep word animation tied to genuine word-level timestamps. Coarse YouTube caption segments stay phrase-level; `SubtitleGen` downgrades karaoke/pop animation honestly when no word timestamps exist.

| Preset | Typeface / treatment | Suggested archetypes |
|---|---|---|
| `hormozi_pop` | Montserrat 76, uppercase, yellow active-word scale pop, heavy black outline | `comedy_banter`, `solo_monologue`, `guest_qa` |
| `neon_glow` | Outfit 70, uppercase, cyan active word and magenta blur glow | `technical_deep_dive`, `debate`, `comedy_banter` |
| `pill_highlight` | Poppins 64, gold active word over an opaque dark box | `guest_qa`, `technical_deep_dive`, `multilingual_hinglish` |
| `editorial_serif` | Playfair Display 60, warm ivory and amber, restrained outline | `personal_narrative`, `solo_monologue`, `debate` |
| `hinglish_impact` | Noto Sans Devanagari 70, saffron pop, never uppercase | `multilingual_hinglish`, `guest_qa`, `personal_narrative` |
| `viral_bounce` | Bangers 82, uppercase, lime active-word pop | `comedy_banter`, `solo_monologue`, `guest_qa` |
| `documentary_clean` | Inter 56, translucent bar and soft blue karaoke fill | `technical_deep_dive`, `personal_narrative`, `debate` |
| `minimal_mono` | JetBrains Mono 54, emerald karaoke fill, compact terminal feel | `technical_deep_dive`, `debate`, `solo_monologue` |

ASS color literals use `&HAABBGGRR`, with BGR channel order. Keep `MarginV` at or above 300 (320 default) and `MarginR` at 120 unless the composition requires a documented change.

## Font Pairings and Unicode

Latin display faces: Montserrat, Outfit, Poppins, Playfair Display, Bangers, Inter, and JetBrains Mono. For Hindi and code-switched captions, pair Latin faces with a Devanagari-capable family such as Noto Sans Devanagari, Khand, Teko, Rozha One, or Tiro Devanagari Hindi. Supply local `.ttf`/`.otf` files through `fonts_dir` for offline libass discovery.

Do not uppercase Devanagari. Apply any Latin casing to raw caption text before ASS escaping; never uppercase generated ASS tags. Preserve combining marks, matras, nukta, emoji sequences, punctuation, and original transcript text. A font fallback is a rendering limitation, not permission to rewrite source words.

## Text Behind a Person (HyperFrames Reference Pattern)

This three-layer pattern is documented for a future HyperFrames composition. The source reference is `.agents/skills/hyperframes-media/references/remove-background.md`.

```bash
npx hyperframes remove-background subject.mp4 -o subject.webm --background-output plate.webm
```

Composite in this order:

1. `plate.webm` at z-index 1, with the subject-shaped transparent hole.
2. A large, short GSAP headline at z-index 2.
3. The wrapped `subject.webm` cutout at z-index 3, synchronized from `data-start="0"` (and `data-media-start="0"`). Animate the wrapper opacity, not the timed video element.

Keep normal dialogue captions in front of the composition and above the mobile lower safe zone. A plate is not inpainted footage; content under its transparent subject hole must be composited deliberately.

## Motion, Transitions, and Sound Effects

- Use whip-pan, zoom, or glitch transitions only when they support a change in idea, energy, or scene. Avoid stacking transitions on every cut.
- Place whoosh/pop/riser effects on the motivating visual or editorial beat; start around volume `0.35` and mix against dialogue before increasing it.
- Respect mobile caption safe zones (`MarginV=320`, `MarginR=120` defaults). Do not place impact text over faces or over the primary caption line.
- Run M5 `MediaQAInspector` on every rendered clip. A failed QA result excludes the clip from `export_bundle`; never bypass that gate for a visual effect.
