"""ToolRegistry adapter for approved vertical clip composition."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig
from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ToolResult, ToolRuntime,
    ToolStability, ToolTier,
)


class VerticalClipCompose(BaseTool):
    name = "vertical_clip_composer"
    version = "1.0.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["cmd:ffmpeg", "cmd:ffprobe"]
    input_schema = {
        "type": "object", "required": ["mode", "source_video_path", "output_dir"],
        "properties": {
            "mode": {"type": "string", "enum": ["approved_batch", "single_clip"], "default": "approved_batch"},
            "script": {"type": "object"}, "plan": {"type": "object"},
            "source_video_path": {"type": "string"}, "output_dir": {"type": "string"},
            "candidate_id": {"type": "string"}, "start_seconds": {"type": "number"}, "end_seconds": {"type": "number"},
            "transcript_segments": {"type": "array"}, "source_manifest": {}, "config": {"type": "object"},
            "shot_cuts": {"type": "array", "items": {"type": "number", "minimum": 0}},
            "speaker_tracks": {"type": "array"},
        },
    }
    output_schema = {"type": "object", "properties": {"clips": {"type": "array"}, "succeeded_count": {"type": "integer"}, "failed_count": {"type": "integer"}}}

    @staticmethod
    def _source_manifest(raw: Any) -> dict | None:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (str, Path)):
            data = json.loads(Path(raw).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("source_manifest JSON must contain an object")
            return data
        raise ValueError("source_manifest must be an object or JSON path")

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        try:
            raw_config = dict(inputs.get("config") or {}) if isinstance(inputs.get("config"), dict) else inputs.get("config")
            if isinstance(raw_config, dict) and isinstance(raw_config.get("emphasis_times"), list):
                raw_config["emphasis_times"] = tuple(float(t) for t in raw_config["emphasis_times"])
            config = VerticalRenderConfig(**raw_config) if isinstance(raw_config, dict) else (raw_config or VerticalRenderConfig())
            composer = VerticalClipComposer()
            manifest = self._source_manifest(inputs.get("source_manifest"))
            shot_cuts = inputs.get("shot_cuts")
            speaker_tracks = inputs.get("speaker_tracks")
            if inputs["mode"] == "approved_batch":
                result = composer.render_approved_batch(
                    script=inputs["script"], plan=inputs["plan"], source_video_path=inputs["source_video_path"],
                    output_dir=inputs["output_dir"], transcript_segments=inputs.get("transcript_segments", []),
                    shot_cuts=shot_cuts, speaker_tracks=speaker_tracks,
                    source_manifest=manifest, config=config,
                )
            elif inputs["mode"] == "single_clip":
                result = composer.render_clip(
                    candidate_id=inputs.get("candidate_id", "clip"),
                    source_video_path=inputs["source_video_path"],
                    start_seconds=inputs["start_seconds"], end_seconds=inputs["end_seconds"],
                    output_dir=inputs["output_dir"],
                    transcript_segments=inputs.get("transcript_segments", []),
                    shot_cuts=shot_cuts, speaker_tracks=speaker_tracks,
                    source_manifest=manifest, config=config,
                )
            else:
                raise ValueError("mode must be approved_batch or single_clip")
            if hasattr(result, "clips"):
                data = asdict(result)
                artifacts = [clip.output_video_path for clip in result.clips if clip.success and clip.output_video_path]
                success = result.failed_count == 0 and result.succeeded_count > 0
            else:
                data = asdict(result)
                artifacts = [result.output_video_path] if result.success and result.output_video_path else []
                success = result.success
            return ToolResult(success=success, data=data, artifacts=artifacts, error=None if success else getattr(result, "error", "one or more renders failed"))
        except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
            return ToolResult(success=False, error=str(exc))
