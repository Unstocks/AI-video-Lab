# Script Director - Clip Factory Pipeline

## Purpose and contracts

This stage turns the source transcript into an evidence-backed candidate dossier and a script view. Read and emit both `schemas/artifacts/clip_selection_plan.schema.json` and `schemas/artifacts/script.schema.json`. Prefer native source captions through `transcript_fetcher`; `transcriber` is optional when native captions are absent. If neither source captions nor an available local STT provider exists, surface a structured blocker instead of inventing dialogue or timestamps. Use `clip_selector` and available `scene_detect`, `silence_cutter`, and `audio_energy` tools as appropriate.

The `clip_selection_plan` is the authoritative editorial record. The `script` is a downstream-facing projection whose metadata must carry the plan SHA-256 and transcript revision. Never invent timestamps, hook wording, evidence, or candidate quality to meet a requested clip count.

## Four-pass process

1. **Transcribe and normalize.** Transcribe the full source, retain the source transcript revision and timing evidence, and use scene detection only to check promising boundaries.
2. **Find and validate moments.** Build candidates from transcript evidence. Every spoken hook must match verbatim source text and carry source spans. Run the five-point cold-viewer audit: subject grounded, entities resolved, pronouns resolved, premise-to-payoff complete, and qualifiers preserved. Consider acoustic and silence evidence without fabricating certainty.
3. **Evaluate and select.** Rank valid, eligible candidates for editorial value and diversity. Apply duplicate and duration rules. A target count is a goal, never a reason to pad weak or invalid clips. If none pass, return the honest rejection/deferred dossier and no dummy script.
4. **Emit synchronized provisional artifacts.** Use `clip_selector` to create `clip_selection_plan.json` and a provisional `script.json`. Verify the script's `clip_selection_plan_sha256`, transcript revision, selected IDs, and section timestamps match the plan.

## Dual-artifact human gate lifecycle (ADR-002)

At `awaiting_human` with `human_approved=False`, write both artifacts: the authoritative plan and the provisional script (`metadata.approval_status="provisional"`). Present the selected, rejected, and deferred candidates and explain any zero-quota result. Then **end the turn** and wait for explicit human decisions.

After explicit approval or edits, call `finalize_approved_selection()` with the user's decisions. Approve only valid and eligible candidates; for boundary revisions, preserve the prior boundary in provenance, set `transformation="human_adjusted"`, and mark provenance human-reviewed. Rejects must remain out of the approved script. Verify the resulting hash and section-to-plan sync, write the updated plan and approved script, then write the script checkpoint as `completed` with `human_approved=True`. Only then may the pipeline advance to `scene_plan`.

## Quality gate

- Spoken-hook evidence is verbatim, source-spanned, and inside the candidate window.
- Each selected moment passes all five cold-viewer checks.
- Script sections and plan candidate IDs, boundaries, transcript revision, and SHA-256 agree.
- No quota padding, invented evidence, or fabricated timing confidence.
