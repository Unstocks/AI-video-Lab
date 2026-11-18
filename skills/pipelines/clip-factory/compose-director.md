# Compose Director - Clip Factory Pipeline

## When To Use

Render each clip and platform variant independently. The important behaviors here are consistency, batch resilience, and clear reporting of partial failures.

## Runtime Routing (HARD CONSTRAINT — Remotion or FFmpeg only)

This pipeline uses the approved Remotion or FFmpeg routes. For vertical clip production, Milestone 4's `VerticalClipComposer` uses FFmpeg trim, reframe, and clip-relative ASS/SRT burn; this route works offline and keeps the output 1080x1920, `yuv420p`, and fast-start. Remotion's `TalkingHead.tsx` remains the optional kinetic-caption runtime when its supported Node runtime is installed. HyperFrames is NOT an approved clip-factory runtime; its caption parity remains deferred.

- If `edit_decisions.render_runtime == "hyperframes"`, stop. Re-open the idea stage so the user can be presented the real constraint and lock `remotion` with a `render_runtime_selection` decision that records `hyperframes` as `rejected_because: "caption-burn parity deferred on clip-factory"`.
- Per AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)": the constraint is NOT an excuse to skip the conversation. The user still gets to see that HyperFrames exists and why it isn't viable here.
- Pass `proposal_packet`/`brief` to `video_compose.execute()` so the in-tool runtime-swap check runs end-to-end.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["edit"]["edit_decisions"]`, `state.artifacts["assets"]["asset_manifest"]` | Clip edits and assets |
| Tools | `vertical_clip_composer`, `media_qa`, `video_trimmer`, `video_compose`, `audio_mixer`, `color_grade` | Render pipeline and final review |
| Media profiles | `lib/media_profiles.py` | Platform targets |

Before rendering approved clip sections, require `verify_script_plan_sync(..., require_approved=True)` to pass. Prefer a valid `proxy_video_path` from `source_manifest.json` while preserving the master file. Generate clip-rebased subtitles with `subtitle_gen` and burn them via FFmpeg's `ass` or `subtitles` filter. Render each clip independently, probe its final dimensions/codec/duration, and continue after a per-clip failure.

For clip-factory vertical batches, invoke `vertical_clip_composer` in `approved_batch` mode with the approved script and plan (`codec="auto"`, `layout_mode="auto"`, `normalize_audio=True`, `scrub_metadata=True`, and the approved `style_preset`). This writes both the rendered `1080x1920` `yuv420p` MP4 and its `<clip>.mp4.layout.json` sidecar while applying `Style: Seam` automatically on `SPLIT` ranges. Then invoke `media_qa` in `batch` mode with every render result, `locked_runtime="ffmpeg"`, `enforce_loudnorm_window=True`, `verify_metadata_scrubbed=True`, and the plan. Persist its schema-valid `final_review` (including per-clip `metadata.clip_reports` with `integrated_lufs` and `true_peak_dbtp`) as `artifacts/final_review.json`. Never mark unchecked QA checks as passing.

## Process

### 1. Treat Each Output As Its Own Job

One clip across three platforms is three render jobs. Name and track them explicitly.

### 2. Reuse What Can Be Shared

- shared audio mix where possible,
- shared subtitle styling,
- shared overlay assets,
- shared grading if the source needs it.

### 3. Fail Softly

If one clip or one platform variant fails:

- log it clearly,
- continue the rest of the batch,
- do not block successful exports.

### 4. Verify Every Output

Per render:

- correct duration,
- correct resolution/aspect ratio,
- no black opening frame,
- hook appears on time,
- subtitles render correctly,
- audio is present and consistent.

### 5. Use Render Report Metadata

Recommended metadata keys:

- `job_index`
- `failed_jobs`
- `shared_intermediates`
- `platform_groupings`

## Common Pitfalls

- Rendering sequentially without reason when jobs are independent.
- Treating a failed clip as a reason to stop the batch.
- Letting one platform variant quietly use the wrong framing or subtitle zone.
