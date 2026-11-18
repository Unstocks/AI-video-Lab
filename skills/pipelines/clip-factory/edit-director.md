# Edit Director - Clip Factory Pipeline

## When To Use

This stage turns the approved clips into independent mini-edits. Each clip must work alone, but the collection should still feel like a coherent series.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["assets"]["asset_manifest"]`, `state.artifacts["scene_plan"]["scene_plan"]`, `state.artifacts["script"]["script"]` | Assets, layouts, transcripts |
| Playbook | Active style playbook | Transition and subtitle consistency |

## Process

### Vertical captions and render handoff (OD-04 / ADR-009)

For clip-factory vertical deliverables, use the offline FFmpeg ASS/SRT path first. Generate clip-relative captions with `subtitle_gen` (`format="ass"` or `"srt"`, choosing a real `style_preset` from `lib/subtitle_styles.py` — e.g. `hinglish_impact`, `hormozi_pop`, `neon_glow`, `pill_highlight`, `editorial_serif`, `viral_bounce`, `documentary_clean`, `minimal_mono`). Use `VerticalClipComposer` (`vertical_clip_composer`) for trim → Smart Reframe v2 (`layout_mode="auto"`, `enable_punch_in=True`, `codec="auto"` for NVENC/x264) → bundled-font ASS subtitle burn after the approved script and `clip_selection_plan` pass `verify_script_plan_sync(require_approved=True)`. On 2-speaker `SPLIT` ranges, `SubtitleGen` automatically routes dialogue to `Style: Seam` (`Alignment=5, MarginV=0`) so captions sit cleanly on the split seam; on single-speaker scenes, keep 9:16 mobile safe zones (`MarginV=320`, `MarginR=120`). Audio is normalized once at trim (`-14 LUFS`, `-2.0 dBTP`, `48 kHz` AAC) and copied downstream (`-c:a copy`), with container metadata scrubbed. The composer prefers the H.264 editing proxy when the source manifest has a valid proxy and records which source it used.

Keep Remotion's `TalkingHead.tsx` path available as the optional kinetic-caption runtime when the supported Node runtime is installed. Do not route this pipeline through HyperFrames; that runtime remains outside the approved clip-factory render choices.

### 1. Build A Shared Edit Template

Lock the batch defaults first:

- subtitle style,
- hook timing,
- lower-third timing,
- watermark behavior,
- audio fade lengths.

Then apply per-clip overrides only where necessary.

### 2. Optimize The First 2-3 Seconds

For every clip:

- start on motion, face, or result,
- show hook text immediately if needed,
- let subtitles begin with the first spoken word,
- avoid intros that delay the point.

### 3. Keep Boundaries Clean

- no cuts mid-word,
- no trailing silence after the point lands,
- no "setup for setup's sake" before the hook,
- no outro cards unless they earn the time.

### 4. Use Metadata For Multi-Variant Detail

Recommended metadata keys:

- `batch_template`
- `clip_variants`
- `hook_windows`
- `cta_windows`

### 5. Quality Gate

- each clip is self-contained,
- the first seconds hook fast,
- overlay stack is readable on mobile,
- the batch retains consistent styling and fades.

## Common Pitfalls

- Building one highlight reel instead of independent clips.
- Letting branding delay the hook.
- Overcrowding the screen with hook text, subtitles, watermark, and lower third simultaneously.
- Applying inconsistent transition timing across the batch.
