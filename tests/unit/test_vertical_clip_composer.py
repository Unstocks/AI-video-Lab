"""Unit tests for the registered vertical_clip_composer BaseTool adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.vertical_composer import ClipRenderResult, VerticalBatchRenderResult, VerticalRenderConfig
from tools.video.vertical_clip_composer import VerticalClipCompose


def test_single_clip_mode_forwards_output_dir_shot_cuts_and_speaker_tracks(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class StubComposer:
        def render_clip(self, **kwargs: Any) -> ClipRenderResult:
            captured.update(kwargs)
            out = str(Path(kwargs["output_dir"]) / f"{kwargs['candidate_id']}.mp4")
            return ClipRenderResult(
                candidate_id=kwargs["candidate_id"],
                success=True,
                output_video_path=out,
                subtitle_path=None,
                source_video_used=str(kwargs["source_video_path"]),
                layout_mode=kwargs["config"].layout_mode,
                duration_seconds=5.0,
                width=1080,
                height=1920,
            )

    monkeypatch.setattr("tools.video.vertical_clip_composer.VerticalClipComposer", StubComposer)
    tool = VerticalClipCompose()
    result = tool.execute({
        "mode": "single_clip",
        "candidate_id": "clip_01",
        "source_video_path": str(tmp_path / "src.mp4"),
        "output_dir": str(tmp_path / "renders"),
        "start_seconds": 10.0,
        "end_seconds": 15.0,
        "shot_cuts": [12.5],
        "speaker_tracks": [{"timestamp_seconds": 11.0, "bbox": {"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2}}],
        "config": {"burn_subtitles": False},
    })

    assert result.success, result.error
    assert captured["candidate_id"] == "clip_01"
    assert captured["output_dir"] == str(tmp_path / "renders")
    assert "output_path" not in captured
    assert captured["shot_cuts"] == [12.5]
    assert len(captured["speaker_tracks"]) == 1
    assert isinstance(captured["config"], VerticalRenderConfig)
    assert result.artifacts == [str(tmp_path / "renders" / "clip_01.mp4")]


def test_approved_batch_mode_forwards_shot_cuts_and_speaker_tracks(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class StubComposer:
        def render_approved_batch(self, **kwargs: Any) -> VerticalBatchRenderResult:
            captured.update(kwargs)
            clip = ClipRenderResult(
                candidate_id="clip_01",
                success=True,
                output_video_path=str(tmp_path / "renders" / "clip_01.mp4"),
                subtitle_path=None,
                source_video_used=str(kwargs["source_video_path"]),
                layout_mode=kwargs["config"].layout_mode,
                duration_seconds=5.0,
                width=1080,
                height=1920,
            )
            return VerticalBatchRenderResult(
                project_id="proj",
                plan_sha256="abc123",
                profile_name="youtube_shorts",
                clips=(clip,),
                succeeded_count=1,
                failed_count=0,
            )

    monkeypatch.setattr("tools.video.vertical_clip_composer.VerticalClipComposer", StubComposer)
    tool = VerticalClipCompose()
    result = tool.execute({
        "mode": "approved_batch",
        "script": {"sections": []},
        "plan": {"candidates": []},
        "source_video_path": str(tmp_path / "src.mp4"),
        "output_dir": str(tmp_path / "renders"),
        "shot_cuts": [4.0, 9.0],
        "speaker_tracks": [{"start_seconds": 0.0, "end_seconds": 5.0, "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2}}],
        "config": {"burn_subtitles": False},
    })

    assert result.success, result.error
    assert captured["shot_cuts"] == [4.0, 9.0]
    assert len(captured["speaker_tracks"]) == 1
    assert result.data["succeeded_count"] == 1

