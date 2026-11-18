"""BaseTool entry point for local video source normalization."""

from __future__ import annotations

import json
from typing import Any

from lib.url_ingest import MediaIngestionError, URLIntakeAdapter, URLValidationError
from tools.base_tool import BaseTool, ToolResult, ToolStability, ToolTier


class LocalMediaIntake(BaseTool):
    name = "local_media_intake"
    version = "1.0.0"
    tier = ToolTier.SOURCE
    capability = "source_ingest"
    provider = "local"
    stability = ToolStability.BETA
    dependencies = ["cmd:ffmpeg", "cmd:ffprobe"]
    input_schema = {
        "type": "object", "required": ["local_path", "project_id", "pipeline_type"],
        "properties": {
            "local_path": {"type": "string"}, "project_id": {"type": "string"},
            "pipeline_type": {"type": "string"}, "transcript_path": {"type": "string"},
            "max_duration_seconds": {"type": "integer", "default": 3600},
            "max_file_size_bytes": {"type": "integer", "default": 2147483648},
        },
    }
    output_schema = {"type": "object", "properties": {
        "video_path": {"type": ["string", "null"]}, "audio_path": {"type": ["string", "null"]},
        "transcript_path": {"type": ["string", "null"]}, "manifest_path": {"type": ["string", "null"]},
        "proxy_video_path": {"type": ["string", "null"]},
    }}

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            adapter = URLIntakeAdapter(pipeline_type=inputs["pipeline_type"])
            result = adapter.ingest_local_file(
                inputs["local_path"], inputs["project_id"], transcript_path=inputs.get("transcript_path"),
                max_duration_seconds=inputs.get("max_duration_seconds", 3600),
                max_file_size_bytes=inputs.get("max_file_size_bytes", 2 * 1024**3),
            )
            data = result.__dict__.copy()
            with open(result.manifest_path, encoding="utf-8") as manifest_file:
                proxy = json.load(manifest_file).get("proxy_video_path")
            data["proxy_video_path"] = proxy
            artifacts = [data[key] for key in ("video_path", "audio_path", "transcript_path", "manifest_path", "proxy_video_path") if data.get(key)]
            return ToolResult(success=result.success, data=data, artifacts=artifacts, error=result.error)
        except (KeyError, TypeError, ValueError, OSError, URLValidationError, MediaIngestionError) as exc:
            return ToolResult(success=False, error=str(exc))
