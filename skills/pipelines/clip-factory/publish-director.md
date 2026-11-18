# Publish Director - Clip Factory Pipeline

## When To Use

This stage packages the clip batch into a distribution plan. The goal is not just exported files. The goal is a usable content engine.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation |
| Prior artifacts | `state.artifacts["compose"]["render_report"]`, `state.artifacts["idea"]["brief"]`, `state.artifacts["script"]["script"]` | Outputs, rankings, and goals |
| Playbook | Active style playbook | Brand voice |

## Process

### 1. Lead With The Strongest Clip

Do not schedule by chronology. Schedule by ranking.

The first published clip should usually be:

- the strongest hook,
- the cleanest standalone clip,
- the clip most aligned with the batch goal.

### 2. Tailor Copy By Platform

Each platform needs its own tone and packaging:

- TikTok / Reels: direct, fast, hook-led
- Shorts: searchable, keyword-aware
- LinkedIn: insight-led and more professional
- X: short, punchy, opinion-friendly

### 3. Package The Batch Cleanly

Use `export_bundle` batch mode with `clips=[...]` to group by platform and include ready-to-paste text assets, not just video files. Rank determines posting order; packages are laid out as `clips/01_<clip_id>/`, `clips/02_<clip_id>/`, and so on, with a root `manifest.json` linking each clip to its package.

### 4. Enforce The Automated QA Gate

Read the schema-valid `final_review.json` before packaging. Pass `final_review`, the approved `clip_selection_plan`, the synchronized approved `script`, and `plan_sha256` to `export_bundle`. Only clips explicitly listed in `metadata.passed_clip_ids` with a passing per-clip report whose SHA-256 matches the current file may export. A failed, missing, stale, or unapproved clip must remain excluded with its reason recorded in `publish_log.json`. If no clips pass QA, stop and surface that result.

### 5. Preserve Batch Truth

Store in `publish_log.metadata` and the export `manifest.json`:

- `clip_catalog`
- `posting_order`
- `skipped_failed_clips`
- `plan_sha256`

The schema-valid `publish_log.json` contains one `exported` or `failed` entry per clip, with per-clip metadata and export paths for successful packages.

### 6. Quality Gate

- strongest clips lead the rollout,
- captions are platform-specific,
- export folders are usable without extra cleanup,
- the batch catalog clearly links ranking, file paths, and publishing intent.

## Common Pitfalls

- Publishing the whole batch on the same day.
- Using one caption everywhere.
- Losing the rank/order logic after rendering is complete.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the summary (the Backlot board renders
the artifact), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.
