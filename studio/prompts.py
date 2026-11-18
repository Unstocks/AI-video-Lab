"""Deterministic structured prompt builders for every Studio UI -> Top-Supervisor directive.

Every interactive action in the Studio UI (Start URL Production, Approve/Reject,
Per-Scene Reframe Override, Word-Snapped Recut, Preset Swap, Export Bundle)
translates into a canonical directive for ``fcc-claude`` so the Top Supervisor
always follows ``AGENT_GUIDE.md`` and ``pipeline_defs/clip-factory.yaml`` cleanly.
"""

from __future__ import annotations

import json
from typing import Any, Sequence


def build_start_job_prompt(
    *,
    source_input: str,
    project_id: str | None = None,
    clip_count: int = 2,
    style_preset: str = "hinglish_impact",
    layout_mode: str = "auto",
    enable_punch_in: bool = True,
) -> str:
    """Build Turn-1 Top-Supervisor mission prompt for URL or local-file clip production."""
    proj_hint = (
        f"Use exact project_id `{project_id}` under `projects/{project_id}/`."
        if project_id
        else "Create a clean slug project_id under `projects/<slug>/`."
    )
    is_url = source_input.strip().lower().startswith(("http://", "https://"))
    intake_tool = "url_intake" if is_url else "local_media_intake"
    return (
        f"You are the Executive Producer / Top Supervisor for AI Video Lab.\n"
        f"Follow `AGENT_GUIDE.md` and `pipeline_defs/clip-factory.yaml` strictly.\n\n"
        f"## Mission Parameters\n"
        f"- Source ({'URL' if is_url else 'Local File'}): `{source_input.strip()}`\n"
        f"- Project: {proj_hint}\n"
        f"- Target Clip Count: up to {int(clip_count)} standalone high-impact clips (never pad with weak clips)\n"
        f"- Render Config (for AFTER human approval): `style_preset=\"{style_preset}\"`, "
        f"`layout_mode=\"{layout_mode}\"`, `enable_punch_in={bool(enable_punch_in)}`, `codec=\"auto\"`\n\n"
        f"## Required Steps (Stop at Human Approval Gate!)\n"
        f"1. Run `{intake_tool}` into `projects/<project_id>/source/` and write `project.json`.\n"
        f"2. Obtain word-level transcript (reuse native captions if present, otherwise `transcriber`).\n"
        f"3. Select up to {int(clip_count)} standalone moments passing verbatim spoken-hook provenance "
        f"and all 5 cold-viewer audit checks via `clip_selector`.\n"
        f"4. Write synchronized `artifacts/script.json` and `artifacts/clip_selection_plan.json`.\n"
        f"5. Write `checkpoint_script.json` with `status=\"awaiting_human\"` and STOP cleanly.\n"
        f"6. Present a concise summary of each candidate (ID, timestamps, verbatim hook, 5/5 audit) "
        f"and wait for the human to click Approve in the Studio UI before rendering."
    )


def build_approval_prompt(
    *,
    project_id: str,
    approved_ids: Sequence[str],
    rejected_ids: Sequence[str] = (),
    style_preset: str | None = None,
    layout_mode: str | None = None,
    enable_punch_in: bool | None = None,
    notes: str = "",
) -> str:
    """Build structured human-approval directive that unlocks RTX 3050 NVENC rendering + QA."""
    cfg_parts = ['codec="auto"', "normalize_audio=True", "scrub_metadata=True"]
    if style_preset:
        cfg_parts.append(f'style_preset="{style_preset}"')
    if layout_mode:
        cfg_parts.append(f'layout_mode="{layout_mode}"')
    if enable_punch_in is not None:
        cfg_parts.append(f"enable_punch_in={bool(enable_punch_in)}")

    lines = [
        f"Human approval received from Studio UI for project `{project_id}`.",
        f"- Approved candidate_ids: {json.dumps(list(approved_ids))}",
        f"- Rejected candidate_ids: {json.dumps(list(rejected_ids))}",
    ]
    if notes.strip():
        lines.append(f"- Human notes: {notes.strip()}")
    lines.extend([
        "",
        "## Execute Now",
        "1. Record `review_state=\"HUMAN_APPROVED\"` (and `HUMAN_REJECTED` for rejected IDs) with "
        "`human_reviewed_at` and `review_metadata=\"Studio UI approval\"` in `artifacts/clip_selection_plan.json`, "
        "and keep `artifacts/script.json` synchronized.",
        "2. Mark `checkpoint_script.json` completed (`human_approved=True`).",
        f"3. Render approved clips into `projects/{project_id}/renders/` using `vertical_clip_composer` "
        f"(`mode=\"approved_batch\"`, config: `{', '.join(cfg_parts)}`).",
        "4. Run `media_qa` on every rendered clip and write `artifacts/final_review.json`.",
        "5. Report each clip's QA status, resolution, codec, integrated LUFS, true peak dBTP, and layout summary.",
    ])
    return "\n".join(lines)


def build_reframe_prompt(
    *,
    project_id: str,
    candidate_id: str,
    crop_overrides: dict[str, Any],
) -> str:
    """Build single-clip per-scene Reframe v2 override re-render directive."""
    overrides_json = json.dumps(crop_overrides, indent=2)
    return (
        f"Per-scene framing override requested from Studio UI for project `{project_id}`, clip `{candidate_id}`.\n\n"
        f"```json\n{overrides_json}\n```\n\n"
        f"## Execute Now\n"
        f"1. Re-render ONLY `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", ...)` "
        f"with `layout_mode=\"auto\"`, `codec=\"auto\"`, and `crop_overrides` set to the JSON above.\n"
        f"2. Re-run `media_qa` on `{candidate_id}` and update `artifacts/final_review.json`.\n"
        f"3. Report the updated layout ranges and QA metrics."
    )


def build_recut_prompt(
    *,
    project_id: str,
    candidate_id: str,
    start_seconds: float,
    end_seconds: float,
) -> str:
    """Build word-snapped transcript In/Out recut directive."""
    return (
        f"Word-snapped recut requested from Studio UI for project `{project_id}`, clip `{candidate_id}`:\n"
        f"- New Start: `{float(start_seconds):.3f}s`\n"
        f"- New End: `{float(end_seconds):.3f}s` (duration `{float(end_seconds) - float(start_seconds):.2f}s`)\n\n"
        f"## Execute Now\n"
        f"1. Update `{candidate_id}` boundaries in `artifacts/clip_selection_plan.json` and `artifacts/script.json`, "
        f"verifying verbatim spoken-hook provenance and all 5 cold-viewer audit checks remain valid.\n"
        f"2. Re-render `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", codec=\"auto\")`.\n"
        f"3. Re-run `media_qa` and update `artifacts/final_review.json`."
    )


def build_style_change_prompt(
    *,
    project_id: str,
    candidate_id: str,
    style_preset: str,
) -> str:
    """Build subtitle preset swap re-render directive for a single clip."""
    return (
        f"Subtitle style preset change requested from Studio UI for project `{project_id}`, clip `{candidate_id}`:\n"
        f"- New `style_preset`: `{style_preset}`\n\n"
        f"## Execute Now\n"
        f"1. Re-render ONLY `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", ...)` "
        f"with `style_preset=\"{style_preset}\"` and `codec=\"auto\"`.\n"
        f"2. Re-run `media_qa` and update `artifacts/final_review.json`."
    )


def build_export_prompt(
    *,
    project_id: str,
    clip_ids: Sequence[str],
) -> str:
    """Build hard-gated export_bundle directive for approved QA_PASSED clips."""
    return (
        f"Export requested from Studio UI for project `{project_id}`:\n"
        f"- Target clip_ids: {json.dumps(list(clip_ids))}\n\n"
        f"## Execute Now\n"
        f"1. Verify every requested clip has `review_state=\"HUMAN_APPROVED\"` and `production_state=\"QA_PASSED\"`.\n"
        f"2. Run `export_bundle` into `projects/{project_id}/exports/` and update `exports/export_manifest.json`.\n"
        f"3. Mark `checkpoint_publish.json` completed and return the exact exported file paths."
    )
