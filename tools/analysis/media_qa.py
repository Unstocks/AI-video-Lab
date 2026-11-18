"""ToolRegistry adapter for deterministic post-render media QA."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lib.media_qa import MediaQAConfig, MediaQAInspector
from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ToolResult, ToolRuntime,
    ToolStability, ToolTier,
)


class MediaQA(BaseTool):
    name = "media_qa"
    version = "1.0.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["cmd:ffmpeg", "cmd:ffprobe"]
    input_schema = {
        "type": "object", "required": ["mode"],
        "properties": {
            "mode": {"type": "string", "enum": ["clip", "batch"]},
            "candidate_id": {"type": "string"}, "video_path": {"type": "string"},
            "expected_duration_seconds": {"type": "number"}, "subtitle_path": {"type": "string"},
            "locked_runtime": {"type": "string", "enum": ["ffmpeg", "remotion", "hyperframes"]},
            "project_id": {"type": "string"}, "render_results": {"type": "array"},
            "plan": {"type": "object"}, "output_path": {"type": "string"},
            "frames_dir": {"type": "string"}, "config": {"type": "object"},
        },
    }
    output_schema = {"type": "object", "properties": {"final_review": {"type": "object"}, "report": {"type": "object"}}}

    @staticmethod
    def _config(raw: Any) -> MediaQAConfig:
        if raw is None:
            return MediaQAConfig()
        if not isinstance(raw, dict):
            raise ValueError("config must be an object")
        return MediaQAConfig(**raw)

    @staticmethod
    def _write_json_atomic(destination: Path, payload: dict[str, Any]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", newline="\n", dir=destination.parent,
                prefix=f".{destination.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            inspector = MediaQAInspector()
            config = self._config(inputs.get("config"))
            if inputs["mode"] == "clip":
                report = inspector.inspect_clip(
                    candidate_id=inputs["candidate_id"], video_path=inputs["video_path"],
                    expected_duration_seconds=inputs.get("expected_duration_seconds"),
                    subtitle_path=inputs.get("subtitle_path"), locked_runtime=inputs.get("locked_runtime"),
                    config=config,
                )
                final_review = report.final_review_artifact
                artifacts = [str(inputs["output_path"])] if inputs.get("output_path") else []
                if inputs.get("output_path"):
                    destination = Path(inputs["output_path"])
                    self._write_json_atomic(destination, final_review)
                return ToolResult(report.status == "pass", data={"report": asdict(report), "final_review": final_review}, artifacts=artifacts)
            if inputs["mode"] != "batch":
                raise ValueError("mode must be clip or batch")
            report = inspector.inspect_batch(
                project_id=inputs["project_id"], render_results=inputs["render_results"],
                plan=inputs.get("plan"), config=config, output_path=inputs.get("output_path"),
                frames_dir=inputs.get("frames_dir"),
            )
            artifacts = [str(inputs["output_path"])] if inputs.get("output_path") else []
            return ToolResult(report.overall_status == "pass", data={
                "report": asdict(report), "final_review": report.final_review,
                "passed_clip_ids": list(report.passed_clip_ids), "failed_clip_ids": list(report.failed_clip_ids),
                "clip_reports": report.final_review["metadata"].get("clip_reports", {}),
                "issues": list(report.issues),
            }, artifacts=artifacts)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            return ToolResult(success=False, error=str(exc))
