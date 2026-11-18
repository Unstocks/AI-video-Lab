"""Scene detection tool wrapping PySceneDetect.

Detects scene boundaries and shot changes in video. Falls back to
FFmpeg-based detection if PySceneDetect is not installed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolStability,
    ToolStatus,
    ToolTier,
)


def _merge_short_scenes(
    bounds: list[tuple[int, int]],
    fps: float,
    min_sec: float = 0.4,
) -> list[tuple[int, int]]:
    """Absorb scenes shorter than ``min_sec`` into an adjacent neighbor.

    Ultra-short flash/transition scenes cause camera-snap bursts and starve
    per-scene strategy sampling in Smart Reframe v2.
    """
    if len(bounds) <= 1 or min_sec <= 0 or fps <= 0:
        return list(bounds)
    min_frames = max(1, int(round(float(min_sec) * float(fps))))

    merged: list[tuple[int, int]] = []
    for s, e in bounds:
        if merged and (e - s) < min_frames:
            prev_s, _prev_e = merged[-1]
            merged[-1] = (prev_s, e)
        else:
            merged.append((s, e))

    # Handle a short leading scene by merging it forward into scene 1.
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_frames:
        merged[1] = (merged[0][0], merged[1][1])
        merged.pop(0)
    return merged


def _merge_short_scene_dicts(scenes: list[dict[str, Any]], min_sec: float = 0.4) -> list[dict[str, Any]]:
    """Time-domain equivalent of ``_merge_short_scenes`` for ``SceneDetect`` output dicts."""
    if len(scenes) <= 1 or min_sec <= 0:
        return scenes
    merged: list[dict[str, Any]] = []
    for scene in scenes:
        start = float(scene["start_seconds"])
        end = float(scene["end_seconds"])
        if merged and (end - start) < min_sec:
            merged[-1]["end_seconds"] = round(end, 3)
            merged[-1]["duration_seconds"] = round(end - float(merged[-1]["start_seconds"]), 3)
        else:
            merged.append({
                "index": len(merged),
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
            })
    if len(merged) > 1 and float(merged[0]["duration_seconds"]) < min_sec:
        merged[1]["start_seconds"] = merged[0]["start_seconds"]
        merged[1]["duration_seconds"] = round(
            float(merged[1]["end_seconds"]) - float(merged[1]["start_seconds"]), 3
        )
        merged.pop(0)
    for i, item in enumerate(merged):
        item["index"] = i
    return merged


class SceneDetect(BaseTool):
    name = "scene_detect"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["cmd:ffmpeg"]
    install_instructions = (
        "FFmpeg is required. For better detection install PySceneDetect:\n"
        "pip install scenedetect[opencv]"
    )
    agent_skills = ["ffmpeg"]

    capabilities = [
        "detect_scenes",
        "detect_content_changes",
        "detect_threshold",
    ]

    input_schema = {
        "type": "object",
        "required": ["input_path"],
        "properties": {
            "input_path": {"type": "string"},
            "method": {
                "type": "string",
                "enum": ["content", "threshold", "adaptive"],
                "default": "content",
            },
            "threshold": {
                "type": "number",
                "description": "Detection threshold (method-dependent)",
            },
            "min_scene_length_seconds": {
                "type": "number",
                "minimum": 0.1,
                "default": 1.0,
            },
            "output_path": {"type": "string", "description": "Path for scene list JSON"},
        },
    }

    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=1024, vram_mb=0, disk_mb=100)
    idempotency_key_fields = ["input_path", "method", "threshold", "min_scene_length_seconds"]
    side_effects = ["writes scene list JSON to output_path"]
    user_visible_verification = [
        "Spot-check detected scene boundaries against the video",
    ]

    def _has_pyscenedetect(self) -> bool:
        try:
            import scenedetect  # noqa: F401
            return True
        except ImportError:
            return False

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        start = time.time()

        if self._has_pyscenedetect():
            scenes = self._detect_pyscenedetect(inputs)
        else:
            scenes = self._detect_ffmpeg(inputs)

        min_merge = float(inputs.get("min_scene_length_seconds", 0.4) or 0.4)
        scenes = _merge_short_scene_dicts(scenes, min_sec=min(0.4, min_merge))

        elapsed = time.time() - start

        # Write scene list
        output_path = Path(
            inputs.get("output_path", str(input_path.with_suffix(".scenes.json")))
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps({"scenes": scenes}, indent=2), encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "scene_count": len(scenes),
                "scenes": scenes,
                "method": "pyscenedetect" if self._has_pyscenedetect() else "ffmpeg",
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
            duration_seconds=round(elapsed, 2),
        )

    def _detect_pyscenedetect(self, inputs: dict[str, Any]) -> list[dict]:
        """Use PySceneDetect for scene detection."""
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector, ThresholdDetector, AdaptiveDetector

        input_path = str(inputs["input_path"])
        method = inputs.get("method", "content")
        threshold = inputs.get("threshold")
        min_scene_len = inputs.get("min_scene_length_seconds", 1.0)

        video = open_video(input_path)
        scene_manager = SceneManager()

        if method == "content":
            detector = ContentDetector(
                threshold=threshold or 27.0,
                min_scene_len=int(min_scene_len * video.frame_rate),
            )
        elif method == "threshold":
            detector = ThresholdDetector(
                threshold=threshold or 12.0,
                min_scene_len=int(min_scene_len * video.frame_rate),
            )
        elif method == "adaptive":
            detector = AdaptiveDetector(
                adaptive_threshold=threshold or 3.0,
                min_scene_len=int(min_scene_len * video.frame_rate),
            )
        else:
            detector = ContentDetector()

        scene_manager.add_detector(detector)
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        scenes = []
        for i, (scene_start, scene_end) in enumerate(scene_list):
            scenes.append({
                "index": i,
                "start_seconds": round(scene_start.get_seconds(), 3),
                "end_seconds": round(scene_end.get_seconds(), 3),
                "duration_seconds": round(
                    scene_end.get_seconds() - scene_start.get_seconds(), 3
                ),
            })

        return scenes

    @staticmethod
    def _escape_lavfi_movie_path(path: str) -> str:
        """Escape a path for FFmpeg lavfi movie=... without allowing filter injection."""
        normalized = path.replace("\\", "/")
        if "'" in normalized:
            raise ValueError("FFmpeg lavfi movie paths containing single quotes are unsupported")
        escaped = []
        for char in normalized:
            if char in "\\:,[];":
                escaped.append("\\" + char)
            else:
                escaped.append(char)
        return "".join(escaped)

    def _detect_ffmpeg(self, inputs: dict[str, Any]) -> list[dict]:
        """Fallback: use FFmpeg scene change filter."""
        input_path = str(inputs["input_path"])
        threshold = inputs.get("threshold", 0.3)
        min_scene_len = inputs.get("min_scene_length_seconds", 1.0)
        escaped_input = self._escape_lavfi_movie_path(input_path)

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-show_entries", "frame=pts_time",
            "-of", "json",
            "-f", "lavfi",
            f"movie='{escaped_input}',select='gt(scene,{threshold})'",
        ]

        try:
            result = self.run_command(cmd, timeout=120)
            data = json.loads(result.stdout)
        except Exception:
            # If ffprobe lavfi approach fails, try a simpler method
            return self._detect_ffmpeg_simple(input_path, threshold, min_scene_len)

        change_points = [0.0]
        for frame in data.get("frames", []):
            ts = float(frame.get("pts_time", 0))
            if ts - change_points[-1] >= min_scene_len:
                change_points.append(ts)

        # Get total duration
        dur_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", input_path,
        ]
        dur_result = self.run_command(dur_cmd)
        total_dur = float(json.loads(dur_result.stdout)["format"]["duration"])
        change_points.append(total_dur)

        scenes = []
        for i in range(len(change_points) - 1):
            start = change_points[i]
            end = change_points[i + 1]
            scenes.append({
                "index": i,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
            })

        return scenes

    def _detect_ffmpeg_simple(
        self, input_path: str, threshold: float, min_scene_len: float
    ) -> list[dict]:
        """Simplest fallback: split into uniform segments."""
        dur_cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", input_path,
        ]
        dur_result = self.run_command(dur_cmd)
        total_dur = float(json.loads(dur_result.stdout)["format"]["duration"])

        # Use select filter to find scene changes via stdout
        cmd = [
            "ffmpeg",
            "-i", input_path,
            "-vf", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-",
        ]
        try:
            result = self.run_command(cmd, timeout=120)
            output = result.stderr
        except Exception:
            output = ""

        import re
        change_points = [0.0]
        for match in re.finditer(r"pts_time:(\d+\.?\d*)", output):
            ts = float(match.group(1))
            if ts - change_points[-1] >= min_scene_len:
                change_points.append(ts)
        change_points.append(total_dur)

        scenes = []
        for i in range(len(change_points) - 1):
            start = change_points[i]
            end = change_points[i + 1]
            scenes.append({
                "index": i,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(end - start, 3),
            })

        return scenes
