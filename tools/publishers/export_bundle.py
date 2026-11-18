"""Local export bundler — the first PUBLISH-tier tool.

Every pipeline ends in a `publish` stage that produces a `publish_log` artifact,
but `tools/publishers/` shipped empty, so the mechanical packaging (copying the
render, writing metadata files, laying out the export directory, and emitting a
schema-valid `publish_log`) had to be hand-rolled by the agent each time.

This tool does that packaging deterministically and locally — no external
account, no upload, no cost. It takes the final render path plus the SEO
metadata the publish-director skill prepares and writes a self-contained export
bundle a creator can hand to any platform, returning a validated `publish_log`
entry with `status: "exported"`.

A networked publisher (e.g. a YouTube uploader) can be added later as a separate
`provider` under the same `publish` capability.
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class ExportBundle(BaseTool):
    name = "export_bundle"
    version = "0.1.0"
    tier = ToolTier.PUBLISH
    capability = "publish"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []  # pure filesystem packaging
    install_instructions = "No setup required — runs locally with the Python standard library."

    agent_skills = []

    capabilities = ["package_export", "write_publish_log"]
    supports = {
        "local_offline": True,
        "free": True,
        "uploads": False,
    }
    best_for = [
        "packaging a finished render for hand-off to any platform",
        "producing a schema-valid publish_log without an external account",
        "offline / no-API-key publishing",
    ]
    not_good_for = [
        "uploading directly to YouTube/TikTok/etc. (no network publish)",
        "generating SEO metadata or thumbnails (the publish-director prepares those)",
    ]

    input_schema = {
        "type": "object",
        "anyOf": [
            {"required": ["video_path", "title"]},
            {"required": ["clips"]},
        ],
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Path to the final rendered video (from render_report.outputs[].path).",
            },
            "title": {"type": "string", "description": "Video title / SEO title."},
            "project_name": {
                "type": "string",
                "description": "Project name; used for the export folder. Defaults to the video's parent-of-parent dir name.",
            },
            "export_dir": {
                "type": "string",
                "description": "Override the export root. Defaults to 'exports/<project_name>'.",
            },
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "chapters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "description": "Either {start_seconds, title} or {time, label}.",
                },
            },
            "subtitles_path": {"type": "string"},
            "thumbnail_path": {"type": "string"},
            "thumbnail_concept": {
                "type": "object",
                "description": "Thumbnail concept JSON when no rendered thumbnail exists.",
            },
            "platform": {
                "type": "string",
                "description": "Target platform label for the publish_log entry. Defaults to 'local'.",
            },
            "visibility": {"type": "string", "enum": ["public", "private", "unlisted"]},
            "timestamp": {
                "type": "string",
                "description": "Override the ISO-8601 timestamp (mainly for deterministic tests).",
            },
            "clips": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "clip_id": {"type": "string"}, "video_path": {"type": "string"},
                    "title": {"type": "string"}, "subtitles_path": {"type": "string"},
                    "thumbnail_path": {"type": "string"}, "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "chapters": {"type": "array", "items": {"type": "object"}},
                    "platform": {"type": "string"}, "visibility": {"type": "string", "enum": ["public", "private", "unlisted"]},
                    "qa_passed": {"type": "boolean"}, "qa_error": {"type": "string"}, "rank": {"type": "integer"},
                }, "additionalProperties": False},
            },
            "plan_sha256": {"type": "string"},
            "final_review": {"type": "object"},
            "clip_selection_plan": {"type": "object"},
            "script": {"type": "object"},
            "require_approval": {"type": "boolean"},
            "overwrite": {"type": "boolean", "default": False},
            "strict_batch": {"type": "boolean", "default": False},
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_log": {"type": "object"},
            "export_path": {"type": "string"},
            "files_written": {"type": "array", "items": {"type": "string"}},
            "exported_count": {"type": "integer"},
            "skipped_failed_clips": {"type": "array", "items": {"type": "string"}},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=0, network_required=False
    )
    side_effects = ["writes an export bundle directory to disk"]
    user_visible_verification = [
        "Open the export folder and confirm the video, metadata, and chapters are present and correct",
    ]

    # ---- Helpers ----

    @staticmethod
    def _format_chapter_time(seconds: float) -> str:
        seconds = int(round(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _chapter_lines(self, chapters: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for ch in chapters:
            label = ch.get("title") or ch.get("label") or ""
            if "start_seconds" in ch or "time_seconds" in ch:
                ts = self._format_chapter_time(ch.get("start_seconds", ch.get("time_seconds", 0)))
            elif "time" in ch:
                ts = str(ch["time"])
            else:
                ts = "0:00"
            lines.append(f"{ts} - {label}".rstrip(" -"))
        return lines

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # ---- Execution ----

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if "clips" in inputs:
            return self._execute_batch(inputs)
        video_path = Path(inputs["video_path"]).expanduser()
        if not video_path.is_file():
            return ToolResult(success=False, error=f"video_path not found: {video_path}")

        final_review = inputs.get("final_review")
        if final_review is not None:
            try:
                from schemas.artifacts import validate_artifact
                validate_artifact("final_review", final_review)
            except Exception as exc:
                return ToolResult(success=False, error=f"final_review failed schema validation: {exc}")
            if final_review.get("status") != "pass":
                return ToolResult(success=False, error="final_review status must be pass for single-video export")
            reviewed_hash = (final_review.get("metadata") or {}).get("video_sha256")
            if not reviewed_hash:
                reports = (final_review.get("metadata") or {}).get("clip_reports") or {}
                for report in reports.values() if isinstance(reports, dict) else ():
                    if isinstance(report, dict) and report.get("video_path") == str(video_path):
                        reviewed_hash = report.get("video_sha256")
                        break
            if reviewed_hash and reviewed_hash != self._sha256(video_path):
                return ToolResult(success=False, error="video file digest does not match final_review")

        title = inputs["title"]
        project_name = inputs.get("project_name") or self._infer_project_name(video_path)

        # Explicitly-provided optional assets must exist — silently dropping them
        # would ship a publish package missing part of an approved deliverable.
        for key in ("subtitles_path", "thumbnail_path"):
            val = inputs.get(key)
            if val and not Path(val).expanduser().is_file():
                return ToolResult(success=False, error=f"{key} provided but not found: {val}")

        export_root = (
            Path(inputs["export_dir"]).expanduser()
            if inputs.get("export_dir")
            else self._default_export_dir(video_path, project_name)
        )

        video_dir = export_root / "video"
        meta_dir = export_root / "metadata"
        thumb_dir = export_root / "thumbnails"
        for d in (video_dir, meta_dir, thumb_dir):
            d.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []

        # Video
        out_video = video_dir / f"output{video_path.suffix or '.mp4'}"
        shutil.copy2(video_path, out_video)
        files_written.append(str(out_video))

        # Subtitles (optional)
        subs_in = inputs.get("subtitles_path")
        if subs_in:
            subs_in = Path(subs_in).expanduser()
            if subs_in.is_file():
                out_subs = video_dir / f"subtitles{subs_in.suffix or '.srt'}"
                shutil.copy2(subs_in, out_subs)
                files_written.append(str(out_subs))

        description = inputs.get("description", "")
        tags = inputs.get("tags", []) or []
        hashtags = inputs.get("hashtags", []) or []
        chapters = inputs.get("chapters", []) or []
        chapter_lines = self._chapter_lines(chapters)

        # metadata.json
        metadata = {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "chapters": chapters,
        }
        meta_json = meta_dir / "metadata.json"
        meta_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        files_written.append(str(meta_json))

        # description.txt (description + chapters appended, ready to paste)
        desc_parts = [description] if description else []
        if chapter_lines:
            desc_parts.append("\n".join(chapter_lines))
        desc_txt = meta_dir / "description.txt"
        desc_txt.write_text("\n\n".join(desc_parts) + ("\n" if desc_parts else ""), encoding="utf-8")
        files_written.append(str(desc_txt))

        # tags.txt (one per line)
        if tags:
            tags_txt = meta_dir / "tags.txt"
            tags_txt.write_text("\n".join(tags) + "\n", encoding="utf-8")
            files_written.append(str(tags_txt))

        # chapters.txt
        if chapter_lines:
            chapters_txt = meta_dir / "chapters.txt"
            chapters_txt.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
            files_written.append(str(chapters_txt))

        # Thumbnail: real image if given, else concept JSON
        thumb_in = inputs.get("thumbnail_path")
        if thumb_in and Path(thumb_in).expanduser().is_file():
            thumb_in = Path(thumb_in).expanduser()
            out_thumb = thumb_dir / f"thumbnail{thumb_in.suffix or '.png'}"
            shutil.copy2(thumb_in, out_thumb)
            files_written.append(str(out_thumb))
        elif inputs.get("thumbnail_concept"):
            concept = thumb_dir / "concept.json"
            concept.write_text(json.dumps(inputs["thumbnail_concept"], indent=2), encoding="utf-8")
            files_written.append(str(concept))

        timestamp = inputs.get("timestamp") or datetime.now(timezone.utc).isoformat()
        entry: dict[str, Any] = {
            "platform": inputs.get("platform", "local"),
            "status": "exported",
            "export_path": str(export_root),
            "timestamp": timestamp,
            "metadata_used": {
                "title": title,
                "description": description,
                "hashtags": hashtags,
                "chapters": chapters,
            },
        }
        if inputs.get("visibility"):
            entry["visibility"] = inputs["visibility"]

        publish_log = {"version": "1.0", "entries": [entry]}
        publish_log["metadata"] = {"qa_verified": bool(final_review)}

        # Validate against the canonical schema so a bad entry fails here, not at checkpoint.
        try:
            from schemas.artifacts import validate_artifact

            validate_artifact("publish_log", publish_log)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(success=False, error=f"publish_log failed schema validation: {exc}")

        return ToolResult(
            success=True,
            data={
                "publish_log": publish_log,
                "export_path": str(export_root),
                "files_written": files_written,
            },
            artifacts=[str(out_video)],
        )

    def _execute_batch(self, inputs: dict[str, Any]) -> ToolResult:
        clips = inputs.get("clips")
        if not isinstance(clips, list) or not clips:
            return ToolResult(success=False, error="clips must be a non-empty list")
        final_review = inputs.get("final_review")
        if not isinstance(final_review, dict) or not final_review:
            return ToolResult(success=False, error="final_review artifact is required and must be schema-valid for batch export")
        try:
            from schemas.artifacts import validate_artifact
            validate_artifact("final_review", final_review)
        except Exception as exc:
            return ToolResult(success=False, error=f"final_review artifact is required and must be schema-valid for batch export: {exc}")
        if final_review.get("status") == "fail":
            return ToolResult(success=False, error="final_review status is fail; batch export is blocked")
        review_meta = final_review.get("metadata") or {}
        passed_raw = review_meta.get("passed_clip_ids") or []
        failed_raw = review_meta.get("failed_clip_ids") or []
        passed_by_qa = set(passed_raw) if isinstance(passed_raw, list) else set()
        failed_by_qa = set(failed_raw) if isinstance(failed_raw, list) else set()
        clip_reports = review_meta.get("clip_reports") or {}
        if not isinstance(clip_reports, dict):
            return ToolResult(success=False, error="final_review metadata.clip_reports must be an object")
        plan = inputs.get("clip_selection_plan")
        script = inputs.get("script")
        require_approval = inputs.get("require_approval")
        if require_approval is None:
            require_approval = bool(plan is not None or script is not None or inputs.get("plan_sha256"))
        if plan is not None or script is not None or require_approval:
            if not isinstance(plan, dict) or not isinstance(script, dict):
                return ToolResult(success=False, error="human approval requires both clip_selection_plan and script")
            try:
                from tools.analysis.clip_selector import verify_script_plan_sync
                from lib.models.clip_plan import ClipSelectionPlan
                normalized_plan = ClipSelectionPlan.model_validate(plan)
                verify_script_plan_sync(script, normalized_plan, require_approved=True)
            except Exception as exc:
                return ToolResult(success=False, error=f"approved script and clip_selection_plan validation failed: {exc}")
            approved_ids = {section.get("id") for section in script.get("sections", []) if isinstance(section, dict)}
            plan_candidates = {candidate.candidate_id: candidate for candidate in normalized_plan.candidates}
        else:
            normalized_plan = None
            approved_ids = set()
            plan_candidates = {}
        input_plan_sha = inputs.get("plan_sha256")
        metadata_plan_sha = review_meta.get("plan_sha256")
        if input_plan_sha and metadata_plan_sha and input_plan_sha != metadata_plan_sha:
            return ToolResult(success=False, error="plan_sha256 does not match final_review metadata")
        if normalized_plan is not None and metadata_plan_sha and normalized_plan.compute_plan_sha256() != metadata_plan_sha:
            return ToolResult(success=False, error="clip_selection_plan SHA-256 does not match final_review metadata")
        seen: set[str] = set()
        normalized: list[tuple[int, dict[str, Any], str]] = []
        for index, clip in enumerate(clips):
            if not isinstance(clip, dict):
                return ToolResult(success=False, error=f"clips[{index}] must be an object")
            clip_id = clip.get("clip_id")
            if not isinstance(clip_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", clip_id) or ".." in clip_id:
                return ToolResult(success=False, error=f"unsafe clip_id in clips[{index}]")
            if clip_id in seen:
                return ToolResult(success=False, error=f"duplicate clip_id: {clip_id}")
            seen.add(clip_id)
            rank = clip.get("rank", index)
            if isinstance(rank, bool) or not isinstance(rank, int):
                return ToolResult(success=False, error=f"rank must be an integer for clip {clip_id}")
            normalized.append((rank, clip, clip_id))
        normalized.sort(key=lambda row: row[0])
        export_root = Path(inputs.get("export_dir") or Path("exports") / (inputs.get("project_name") or "clips")).expanduser()
        timestamp = inputs.get("timestamp") or datetime.now(timezone.utc).isoformat()
        entries: list[dict[str, Any]] = []
        files_written: list[str] = []
        exported_paths: list[str] = []
        skipped_failed: list[str] = []
        exported_ids: list[str] = []
        catalog: list[dict[str, Any]] = []
        posting_order: list[str] = []
        clips_root = export_root / "clips"

        def metadata_for(clip: dict[str, Any]) -> dict[str, Any]:
            return {
                "title": str(clip.get("title") or clip.get("clip_id") or "Untitled clip"),
                "description": str(clip.get("description") or ""),
                "hashtags": clip.get("hashtags", []) or [],
                "chapters": clip.get("chapters", []) or [],
            }

        def failed_entry(clip: dict[str, Any], reason: str) -> dict[str, Any]:
            return {
                "platform": str(clip.get("platform") or "local"), "status": "failed",
                "timestamp": timestamp,
                "error": str(clip.get("qa_error") or reason),
                "metadata_used": metadata_for(clip),
            }

        for position, (rank, clip, clip_id) in enumerate(normalized, start=1):
            platform = str(clip.get("platform") or "local")
            metadata = metadata_for(clip)
            qa_record = clip_reports.get(clip_id)
            video_path = Path(str(clip.get("video_path") or "")).expanduser()
            qa_rejection = None
            if clip.get("qa_passed") is False or clip_id in failed_by_qa:
                qa_rejection = "excluded: clip failed automated media QA"
            elif clip_id not in passed_by_qa:
                qa_rejection = "excluded: clip is absent from the final_review passing allowlist"
            elif not isinstance(qa_record, dict):
                qa_rejection = "excluded: final_review has no per-clip QA report"
            elif qa_record.get("production_state") != "QA_PASSED" or qa_record.get("status") != "pass":
                qa_rejection = "excluded: per-clip QA report is not passing"
            elif not video_path.is_file():
                qa_rejection = f"video_path not found: {video_path}"
            elif not qa_record.get("video_sha256") or qa_record["video_sha256"] != self._sha256(video_path):
                qa_rejection = "excluded: video file digest does not match final_review"
            if qa_rejection:
                skipped_failed.append(clip_id)
                entries.append(failed_entry(clip, qa_rejection))
                catalog.append({"clip_id": clip_id, "rank": rank, "status": "failed", "title": metadata["title"]})
                continue
            subs_value, thumb_value = clip.get("subtitles_path"), clip.get("thumbnail_path")
            missing = None
            if not video_path.is_file():
                missing = f"video_path not found: {video_path}"
            elif subs_value and not Path(subs_value).expanduser().is_file():
                missing = f"subtitles_path provided but not found: {subs_value}"
            elif thumb_value and not Path(thumb_value).expanduser().is_file():
                missing = f"thumbnail_path provided but not found: {thumb_value}"
            if missing:
                skipped_failed.append(clip_id)
                entries.append(failed_entry(clip, missing))
                catalog.append({"clip_id": clip_id, "rank": rank, "status": "failed", "title": metadata["title"]})
                continue
            ordinal = position
            clip_dir = clips_root / f"{ordinal:02d}_{clip_id}"
            staging_dir = clips_root / f".staging_{clip_id}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            backup_dir = clips_root / f".backup_{clip_id}_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            overwrite = bool(inputs.get("overwrite", False))
            if clip_dir.exists() and not overwrite:
                skipped_failed.append(clip_id)
                entries.append(failed_entry(clip, "export destination already exists (set overwrite=True to replace)"))
                catalog.append({"clip_id": clip_id, "rank": rank, "status": "failed", "title": metadata["title"]})
                continue
            try:
                clips_root.mkdir(parents=True, exist_ok=True)
                staging_dir.mkdir(parents=False, exist_ok=False)
                out_video = staging_dir / "video.mp4"
                shutil.copy2(video_path, out_video)
                if subs_value:
                    source = Path(subs_value).expanduser()
                    out_subs = staging_dir / f"subtitles{source.suffix or '.srt'}"
                    shutil.copy2(source, out_subs)
                if thumb_value:
                    source = Path(thumb_value).expanduser()
                    out_thumb = staging_dir / f"thumbnail{source.suffix or '.png'}"
                    shutil.copy2(source, out_thumb)
                if clip.get("tags"):
                    metadata["tags"] = clip["tags"]
                metadata_path = staging_dir / "metadata.json"
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                description = metadata["description"]
                desc_path = staging_dir / "description.txt"
                desc_path.write_text(description + ("\n" if description else ""), encoding="utf-8")
                if clip.get("tags"):
                    tags_path = staging_dir / "tags.txt"
                    tags_path.write_text("\n".join(clip["tags"]) + "\n", encoding="utf-8")
                chapter_lines = self._chapter_lines(clip.get("chapters", []) or [])
                if chapter_lines:
                    chapters_path = staging_dir / "chapters.txt"
                    chapters_path.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
                if clip_dir.exists():
                    os.replace(clip_dir, backup_dir)
                try:
                    os.replace(staging_dir, clip_dir)
                except Exception:
                    if backup_dir.exists() and not clip_dir.exists():
                        os.replace(backup_dir, clip_dir)
                    raise
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                files_written.extend(str(path) for path in sorted(clip_dir.iterdir()))
                exported_paths.append(str(clip_dir / "video.mp4"))
                entry = {
                    "platform": platform, "status": "exported", "export_path": str(clip_dir),
                    "timestamp": timestamp, "metadata_used": metadata_for(clip),
                }
                if clip.get("visibility"):
                    entry["visibility"] = clip["visibility"]
                entries.append(entry)
                exported_ids.append(clip_id)
                posting_order.append(clip_id)
                catalog.append({"clip_id": clip_id, "rank": rank, "status": "exported", "title": metadata["title"], "export_path": str(clip_dir)})
            except Exception as exc:
                shutil.rmtree(staging_dir, ignore_errors=True)
                if backup_dir.exists() and not clip_dir.exists():
                    os.replace(backup_dir, clip_dir)
                skipped_failed.append(clip_id)
                entries.append(failed_entry(clip, f"export failed: {exc}"))
                catalog.append({"clip_id": clip_id, "rank": rank, "status": "failed", "title": metadata["title"]})

        plan_sha = inputs.get("plan_sha256")
        manifest = {
            "version": "1.0", "project_name": str(inputs.get("project_name") or export_root.name),
            "generated_at": timestamp, "plan_sha256": plan_sha, "posting_order": posting_order,
            "exported_clip_ids": exported_ids, "skipped_failed_clips": skipped_failed,
            "clip_catalog": catalog,
        }
        batch_status = "complete" if exported_ids and not skipped_failed else "partial" if exported_ids else "failed"
        if exported_ids:
            export_root.mkdir(parents=True, exist_ok=True)
            manifest_path = export_root / "manifest.json"
            temp_manifest = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
            try:
                temp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(temp_manifest, manifest_path)
            finally:
                temp_manifest.unlink(missing_ok=True)
            files_written.append(str(manifest_path))
        publish_log = {
            "version": "1.0", "entries": entries,
            "metadata": {
                "batch_mode": True, "exported_count": len(exported_ids),
                "skipped_failed_clips": skipped_failed, "posting_order": posting_order,
                "clip_catalog": catalog, "plan_sha256": plan_sha,
                "batch_status": batch_status, "failed_count": len(skipped_failed),
            },
        }
        try:
            from schemas.artifacts import validate_artifact
            validate_artifact("publish_log", publish_log)
        except Exception as exc:
            return ToolResult(success=False, error=f"publish_log failed schema validation: {exc}", data={"publish_log": publish_log})
        data = {
            "publish_log": publish_log, "export_path": str(export_root), "files_written": files_written,
            "exported_count": len(exported_ids), "skipped_failed_clips": skipped_failed,
            "batch_status": batch_status, "failed_count": len(skipped_failed),
        }
        if not exported_ids:
            return ToolResult(success=False, error="no QA-passed clips available to export", data=data)
        if inputs.get("strict_batch", False) and skipped_failed:
            return ToolResult(success=False, error="strict batch export failed because one or more clips were rejected", data=data, artifacts=exported_paths)
        return ToolResult(success=True, data=data, artifacts=exported_paths)

    @staticmethod
    def _default_export_dir(video_path: Path, project_name: str) -> Path:
        """Keep run output inside the project workspace.

        When the render lives at ``projects/<name>/renders/...`` (the OpenMontage
        convention), default the bundle to ``projects/<name>/exports/`` alongside
        ``artifacts/``, ``assets/`` and ``renders/``. Otherwise fall back to a
        top-level ``exports/<project_name>/``.
        """
        resolved = video_path.resolve()
        if resolved.parent.name == "renders":
            return resolved.parent.parent / "exports"
        return Path("exports") / project_name

    @staticmethod
    def _infer_project_name(video_path: Path) -> str:
        # projects/<name>/renders/final.mp4 -> <name>; fall back to the file stem.
        parents = video_path.resolve().parents
        if len(parents) >= 2:
            return parents[1].name
        return video_path.stem
