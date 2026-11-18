"""Deterministic structured prompt builders for every Studio UI -> Top-Supervisor directive.

Aligned 100% with ``AGENT_GUIDE.md``, ``pipeline_defs/clip-factory.yaml``,
``tools/analysis/clip_selector.py`` (``finalize_approved_selection``),
``lib/media_qa.py``, and ``tools/publishers/export_bundle.py`` (``exports/manifest.json``).
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
        f"- Planned Render Config (for AFTER human approval): `style_preset=\"{style_preset}\"`, "
        f"`layout_mode=\"{layout_mode}\"`, `enable_punch_in={bool(enable_punch_in)}`, `codec=\"auto\"`, "
        f"`normalize_audio=True`, `scrub_metadata=True`\n\n"
        f"## Required Steps (Stop at Human Approval Gate!)\n"
        f"1. Run `{intake_tool}` into `projects/<project_id>/source/` and initialize `project.json`.\n"
        f"2. Obtain word-level transcript (reuse native captions if present, otherwise `transcriber`).\n"
        f"3. Select up to {int(clip_count)} standalone moments passing verbatim spoken-hook provenance "
        f"and all 5 cold-viewer audit checks via `clip_selector`.\n"
        f"4. Write synchronized provisional `artifacts/script.json` and `artifacts/clip_selection_plan.json`.\n"
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
    """Build structured human-approval directive using ``finalize_approved_selection``."""
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
        "1. Call `finalize_approved_selection()` with these explicit human decisions "
        "(`HUMAN_APPROVED` for approved IDs, `HUMAN_REJECTED` for rejected IDs, `review_metadata=\"Studio UI approval\"`) "
        "to write synchronized `artifacts/clip_selection_plan.json` and approved `artifacts/script.json`, "
        "and verify `verify_script_plan_sync(..., require_approved=True)`.",
        "2. Mark `checkpoint_script.json` completed (`human_approved=True`).",
        f"3. Render approved clips into `projects/{project_id}/renders/` using `vertical_clip_composer` "
        f"(`mode=\"approved_batch\"`, config: `{', '.join(cfg_parts)}`).",
        f"4. Run `media_qa` in `batch` mode with `locked_runtime=\"ffmpeg\"`, `enforce_loudnorm_window=True`, "
        f"and `verify_metadata_scrubbed=True`, persisting `projects/{project_id}/artifacts/final_review.json`.",
        "5. Report each clip's QA status, resolution, codec, integrated LUFS, true peak dBTP, and layout summary.",
    ])
    return "\n".join(lines)


def build_reframe_prompt(
    *,
    project_id: str,
    candidate_id: str,
    crop_overrides: dict[str, Any],
    style_preset: str | None = None,
    enable_punch_in: bool | None = None,
) -> str:
    """Build single-clip per-scene Reframe v2 override re-render directive."""
    overrides_json = json.dumps(crop_overrides, indent=2)
    preserve = ["`layout_mode=\"auto\"`", "`codec=\"auto\"`"]
    if style_preset:
        preserve.append(f"`style_preset=\"{style_preset}\"`")
    else:
        preserve.append("the clip's current `style_preset`")
    if enable_punch_in is not None:
        preserve.append(f"`enable_punch_in={bool(enable_punch_in)}`")
    return (
        f"Per-scene framing override requested from Studio UI for project `{project_id}`, clip `{candidate_id}`.\n\n"
        f"```json\n{overrides_json}\n```\n\n"
        f"## Execute Now\n"
        f"1. Re-render ONLY `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", ...)` "
        f"preserving {', '.join(preserve)}, with `crop_overrides` set to the JSON above.\n"
        f"2. Re-run `media_qa` (`batch` mode across rendered clips) and update `projects/{project_id}/artifacts/final_review.json`.\n"
        f"3. Report the updated layout ranges and QA metrics."
    )


def build_recut_prompt(
    *,
    project_id: str,
    candidate_id: str,
    start_seconds: float,
    end_seconds: float,
    style_preset: str | None = None,
    layout_mode: str | None = None,
) -> str:
    """Build word-snapped transcript In/Out recut directive preserving provenance & styling."""
    preserve = ["`codec=\"auto\"`"]
    preserve.append(f"`style_preset=\"{style_preset}\"`" if style_preset else "the clip's current `style_preset`")
    preserve.append(f"`layout_mode=\"{layout_mode}\"`" if layout_mode else "the clip's current `layout_mode`")
    return (
        f"Word-snapped recut requested from Studio UI for project `{project_id}`, clip `{candidate_id}`:\n"
        f"- New Start: `{float(start_seconds):.3f}s`\n"
        f"- New End: `{float(end_seconds):.3f}s` (duration `{float(end_seconds) - float(start_seconds):.2f}s`)\n\n"
        f"## Execute Now\n"
        f"1. Update `{candidate_id}` boundaries via `finalize_approved_selection()` (`transformation=\"human_adjusted\"`), "
        f"verifying verbatim spoken-hook provenance and all 5 cold-viewer audit checks remain valid, and re-sync `script.json` & `clip_selection_plan.json`.\n"
        f"2. Re-render `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", ...)` preserving {', '.join(preserve)}.\n"
        f"3. Re-run `media_qa` and update `projects/{project_id}/artifacts/final_review.json`."
    )


def build_style_change_prompt(
    *,
    project_id: str,
    candidate_id: str,
    style_preset: str,
    layout_mode: str | None = None,
) -> str:
    """Build subtitle preset swap re-render directive preserving active framing."""
    layout_note = f"`layout_mode=\"{layout_mode}\"`" if layout_mode else "the clip's existing `layout_mode` and any saved `crop_overrides`"
    return (
        f"Subtitle style preset change requested from Studio UI for project `{project_id}`, clip `{candidate_id}`:\n"
        f"- New `style_preset`: `{style_preset}`\n\n"
        f"## Execute Now\n"
        f"1. Re-render ONLY `{candidate_id}` via `vertical_clip_composer(mode=\"single_clip\", ...)` "
        f"with `style_preset=\"{style_preset}\"`, `codec=\"auto\"`, and preserving {layout_note}.\n"
        f"2. Re-run `media_qa` and update `projects/{project_id}/artifacts/final_review.json`."
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
        f"1. Verify every requested clip has `review_state=\"HUMAN_APPROVED\"` and `production_state=\"QA_PASSED\"` "
        f"in `projects/{project_id}/artifacts/final_review.json`.\n"
        f"2. Run `export_bundle` in batch mode (`clips=[...]`, passing `final_review`, `clip_selection_plan`, `script`, and `plan_sha256`) "
        f"into `projects/{project_id}/exports/` so `projects/{project_id}/exports/manifest.json` and `artifacts/publish_log.json` are written.\n"
        f"3. Mark `checkpoint_publish.json` completed and return the exact exported file paths."
    )


def build_production_prompt(
    *,
    pipeline_type: str,
    brief_prompt: str,
    project_id: str | None = None,
    source_input: str | None = None,
    reference_url: str | None = None,
    style_playbook: str | None = None,
    media_profile: str | None = None,
    render_runtime: str | None = None,
    style_preset: str | None = None,
    budget_usd: float | None = None,
    clip_count: int = 2,
    layout_mode: str = "auto",
    enable_punch_in: bool = True,
) -> str:
    """Build Turn-1 Executive Producer prompt for ANY OpenMontage pipeline."""
    if pipeline_type == "clip-factory" and source_input and not reference_url:
        base = build_start_job_prompt(
            source_input=source_input,
            project_id=project_id,
            clip_count=clip_count,
            style_preset=style_preset or "hinglish_impact",
            layout_mode=layout_mode,
            enable_punch_in=enable_punch_in,
        )
        if brief_prompt.strip():
            base += f"\n\n## Additional Creative Direction\n{brief_prompt.strip()}"
        return base

    proj_hint = (
        f"Use exact project_id `{project_id}` under `projects/{project_id}/`."
        if project_id
        else "Create a clean slug project_id under `projects/<slug>/`."
    )
    lines = [
        "You are the Executive Producer / Top Supervisor for AI Video Lab (OpenMontage).",
        f"Follow `AGENT_GUIDE.md` Rule Zero and `pipeline_defs/{pipeline_type}.yaml` strictly.",
        "",
        "## Production Brief",
        f"- Pipeline: `{pipeline_type}`",
        f"- Project: {proj_hint}",
        f"- Creative Brief: {brief_prompt.strip()}",
    ]
    if source_input and source_input.strip():
        lines.append(f"- Source Footage / Media: `{source_input.strip()}`")
    if reference_url and reference_url.strip():
        lines.append(
            f"- Reference Video (Inspiration — follow `skills/meta/video-reference-analyst.md`): `{reference_url.strip()}`"
        )
    if style_playbook:
        lines.append(f"- Style Playbook: `styles/{style_playbook}.yaml`")
    if media_profile:
        lines.append(f"- Target Media Profile: `{media_profile}`")
    if render_runtime:
        lines.append(f"- Preferred Composition Runtime: `{render_runtime}`")
    if style_preset:
        lines.append(f"- Subtitle Style Preset: `{style_preset}`")
    if budget_usd is not None:
        lines.append(f"- Budget Cap: `${float(budget_usd):.2f}` USD")

    lines.extend([
        "",
        "## Required Execution Contract",
        f"1. Read `pipeline_defs/{pipeline_type}.yaml` and run preflight tool discovery (`registry.provider_menu_summary()`).",
        "2. Initialize `projects/<project_id>/project.json` and log every major provider/model/runtime decision to `artifacts/decision_log.json`.",
        "3. Read the exact stage director skill (`skills/pipelines/<pipeline>/<stage>-director.md`) before each stage.",
        "4. Stop cleanly at the FIRST human-gated stage with `status=\"awaiting_human\"` in its `checkpoint_<stage>.json`.",
        "5. Present a crisp executive summary (concepts, tool plan, estimated cost, and next gate) and wait for human approval in Studio UI.",
    ])
    return "\n".join(lines)


def build_gate_decision_prompt(
    *,
    project_id: str,
    stage: str,
    decision: str,
    notes: str = "",
) -> str:
    """Build universal human gate decision directive for any gated pipeline stage."""
    norm = decision.strip().lower()
    if norm == "approve":
        action_lines = [
            f"1. Mark `projects/{project_id}/checkpoint_{stage}.json` completed with `human_approved=True`.",
            "2. Proceed to the next stage in the pipeline manifest, reading its stage director skill first.",
            "3. Stop again cleanly at the next human-gated stage (or complete `publish` if this was the final gate).",
        ]
    elif norm == "revise":
        action_lines = [
            f"1. Keep `projects/{project_id}/checkpoint_{stage}.json` in revision (`in_progress` -> `awaiting_human`).",
            f"2. Apply the human's revision notes to stage `{stage}` artifacts and re-run self-review.",
            "3. Present the updated revision summary and wait for re-approval.",
        ]
    else:
        action_lines = [
            f"1. Record human rejection on `projects/{project_id}/checkpoint_{stage}.json` (`human_approved=False`) and log the reason in `decision_log.json`.",
            "2. Propose concrete alternative directions before spending any further budget.",
        ]

    lines = [
        f"Human Gate Decision from Studio UI for project `{project_id}`:",
        f"- Stage: `{stage}`",
        f"- Decision: `{norm.upper()}`",
    ]
    if notes.strip():
        lines.append(f"- Human Feedback: {notes.strip()}")
    lines.extend(["", "## Execute Now", *action_lines])
    return "\n".join(lines)
