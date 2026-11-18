# Scene Director - Clip Factory Pipeline

## When To Use

You are planning how each selected clip will be framed and packaged for its destination platform. This is where clip viability gets proven or disproven.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["script"]["script"]`, `state.artifacts["idea"]["brief"]` | Selected clips and platform goals |
| Tools | `frame_sampler`, `scene_detect`, `auto_reframe` | Visual checks, shot boundaries, and vertical framing |
| Playbook | Active style playbook | Layout language and safe zones |

## Process

### 1. Choose The Right Frame For Each Clip

Do not default every clip to `9:16`.

Use:

- `9:16` when a face-first crop works,
- `1:1` when speaker plus context both matter,
- `16:9` when slides, demos, or multi-speaker width are essential.

OpenMontage provides Smart Reframe v2 via `auto_reframe` (backed by YuNet `face_tracker`, `SmoothedCameraman` heavy-tripod damping, `split_layout`, `active_speaker`, and smoothstep `punch_in`). Choose its `layout_mode` honestly:

- `auto` (recommended default for podcasts/interviews) — automatically classifies each scene into `TRACK` (single face with 3-frame jump confirm), `SPLIT` (2-speaker stacked vertical gated by `active_speaker.is_conversation()`), or `GENERAL` (42%-height quarter-res blurred backdrop), and writes `<clip>.mp4.layout.json`,
- `speaker_cut` — hard-cuts between two speakers on active-speaker windows (`ALTERNATE`) instead of stacking,
- `single_crop` for an explicit single speaker-centered crop,
- `blurred_pillarbox` for slides, demos, or wide shots where preserving the full frame matters,
- `stacked_split` for an explicit two-speaker vertical stack.

Enable `enable_punch_in=True` for subtle `1.12x` smoothstep emphasis zooms on audio/editorial beats, and pass per-scene `crop_overrides` when the human overrides framing in the Studio UI. Pass `shot_cuts` when scene boundaries are known so crop smoothing resets cleanly at edits. If a crop weakens important context, use a layout that preserves it or plan a safer aspect ratio.

### 2. Plan First-Second Composition

For each clip, define:

- what the viewer sees on frame 1,
- where hook text can safely appear,
- where subtitles can live,
- whether the speaker needs a punch-in or whether the original framing is already good.

### 3. Standardize The Batch

Use the scene plan to lock series consistency:

- same top hook zone,
- same subtitle zone,
- same watermark / brand area,
- same lower-third logic.

### 4. Store Reframe Detail In Metadata

The schema is generic, so store richer layout notes in `scene_plan.metadata`.

Recommended metadata keys:

- `clip_layouts`
- `safe_zones`
- `crop_variants`
- `speaker_positions`
- `platform_variants`

### 5. Use Scenes To Represent Deliverables

Each scene should map to one clip variant or one clip family deliverable. Keep `description` human-readable and use `required_assets` for hook overlays, lower thirds, or branded frames.

### 6. Quality Gate

- every clip has a platform-aware framing plan,
- hook and subtitle zones do not collide,
- weak vertical crops are downgraded honestly,
- the batch will feel visually consistent when rendered together.

## Common Pitfalls

- Center-cropping a wide shot and calling it vertical optimization.
- Ignoring slide or screen-share content while focusing only on faces.
- Letting each clip invent its own layout.
- Forgetting that the first frame determines whether a viewer keeps watching.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
