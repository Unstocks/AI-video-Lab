"""BaseTool entry point for validated remote source intake."""

from typing import Any

from tools.base_tool import BaseTool, ToolResult, ToolTier, ToolStability
from lib.url_ingest import URLIntakeAdapter, URLValidationError, DiskSpaceError, MediaIngestionError


class URLIntake(BaseTool):
    name = "url_intake"
    version = "1.0.0"
    tier = ToolTier.SOURCE
    capability = "source_ingest"
    provider = "openmontage"
    stability = ToolStability.BETA
    dependencies = ["python:yt_dlp", "cmd:ffmpeg", "cmd:ffprobe"]
    output_schema = {"type": "object", "properties": {"success": {"type": "boolean"}, "video_path": {"type": ["string", "null"]}, "audio_path": {"type": ["string", "null"]}, "transcript_path": {"type": ["string", "null"]}, "manifest_path": {"type": ["string", "null"]}, "proxy_video_path": {"type": ["string", "null"]}}}
    input_schema = {
        "type": "object", "required": ["url", "project_id", "pipeline_type"],
        "properties": {
            "url": {"type": "string"}, "project_id": {"type": "string"},
            "pipeline_type": {"type": "string"},
            "max_duration_seconds": {"type": "integer", "default": 3600},
            "caption_languages": {"type": "array", "items": {"type": "string"}, "default": ["en", "hi"]},
        },
    }

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            adapter = URLIntakeAdapter(pipeline_type=inputs["pipeline_type"])
            result = adapter.ingest_url(
                inputs["url"], inputs["project_id"],
                max_duration_seconds=inputs.get("max_duration_seconds", 3600),
                caption_languages=inputs.get("caption_languages", ["en", "hi"]),
            )
        except (URLValidationError, DiskSpaceError, MediaIngestionError) as exc:
            return ToolResult(success=False, error=str(exc))
        data = result.__dict__.copy()
        artifacts = [data[k] for k in ("video_path", "audio_path", "transcript_path", "manifest_path") if data.get(k)]
        if data.get("manifest_path"):
            import json
            with open(data["manifest_path"], encoding="utf-8") as f:
                proxy = json.load(f).get("proxy_video_path")
            if proxy:
                artifacts.append(proxy)
        else:
            proxy = None
        data["proxy_video_path"] = proxy
        return ToolResult(success=result.success, data=data, artifacts=artifacts, error=result.error)
