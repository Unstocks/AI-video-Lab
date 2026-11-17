"""Real local FFmpeg proof for approved clips -> QA -> batch export -> Backlot."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backlot.state import load_board_state
from lib.checkpoint import init_project, write_checkpoint
from lib.media_qa import MediaQAInspector
from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig
from schemas.artifacts import validate_artifact
from tools.analysis.clip_selector import ClipSelector, finalize_approved_selection
from tools.publishers.export_bundle import ExportBundle


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg/ffprobe required")


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True, timeout=180)


def _probe(path: Path) -> dict:
    return json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    ).stdout)


def _candidate(candidate_id: str, text: str, start: float, end: float) -> dict:
    return {
        "candidate_id": candidate_id, "start_seconds": start, "end_seconds": end,
        "original_spoken_dialogue": text, "spoken_opening": text,
        "spoken_hook_text": text, "editorial_title": f"Moment {candidate_id}",
        "cold_viewer_audit": {
            "subject_grounded": True, "entities_resolved": True, "pronouns_resolved": True,
            "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": True,
        },
        "editorial_scores": [{"dimension": "hook_pull", "rationale": "Specific and source-grounded opening.", "score": .9}],
    }


def _checkpoint_all_preceding(projects: Path, project_id: str, project_dir: Path, script: dict, plan: dict) -> None:
    brief = {
        "version": "1.0", "title": "Two grounded moments", "hook": "A practical lesson",
        "key_points": ["Inspect", "Improve"], "tone": "clear", "style": "clean-professional",
        "target_platform": "youtube", "target_duration_seconds": 30,
    }
    write_checkpoint(projects, project_id, "idea", "completed", {"brief": brief}, pipeline_type="clip-factory", human_approved=True)
    write_checkpoint(projects, project_id, "script", "completed", {"script": script, "clip_selection_plan": plan},
                     pipeline_type="clip-factory", human_approved=True)
    write_checkpoint(projects, project_id, "scene_plan", "completed", {"scene_plan": {"version": "1.0", "scenes": [
        {"id": "scene-1", "type": "talking_head", "description": "Approved clip batch", "start_seconds": 0, "end_seconds": 5.5},
    ]}},
                     pipeline_type="clip-factory", human_approved=True)
    write_checkpoint(projects, project_id, "assets", "completed", {"asset_manifest": {"version": "1.0", "assets": []}},
                     pipeline_type="clip-factory", human_approved=True)
    write_checkpoint(projects, project_id, "edit", "completed", {"edit_decisions": {"version": "1.0", "cuts": [], "render_runtime": "ffmpeg"}},
                     pipeline_type="clip-factory", human_approved=True)


def test_clip_factory_render_qa_export_and_backlot(tmp_path):
    project_id = "m5-export-qa"
    projects = tmp_path / "projects"
    project_dir = init_project(project_id, title="M5 export QA", pipeline_type="clip-factory", pipeline_dir=projects)
    source = tmp_path / "source.mp4"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0x3296c8:s=1920x1080:r=25:d=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
    ])
    transcript_text = [
        "The first lesson is to measure the real problem before acting.",
        "The second lesson is to test the smallest useful solution.",
    ]
    transcript = {"transcript": [
        {"text": transcript_text[0], "start": 0.0, "duration": 2.5},
        {"text": transcript_text[1], "start": 3.0, "duration": 2.5},
    ]}
    selected = ClipSelector().execute({
        "project_id": project_id, "source_media_ref": str(source), "transcript": transcript,
        "transcript_format": "youtube", "min_duration_seconds": 1.0,
        "max_duration_seconds": 10.0, "preferred_max_duration_seconds": 10.0,
        "max_clips": 2, "generated_at": "2026-11-17T12:00:00Z",
        "candidates": [
            _candidate("lesson-one", transcript_text[0], 0.0, 2.5),
            _candidate("lesson-two", transcript_text[1], 3.0, 5.5),
        ],
    })
    assert selected.success, selected.error
    plan, script, _ = finalize_approved_selection(
        selected.data["plan"], [
            {"candidate_id": "lesson-one", "action": "approve", "review_metadata": "Approved for rendering."},
            {"candidate_id": "lesson-two", "action": "approve", "review_metadata": "Approved for rendering."},
        ], reviewed_at="2026-11-17T12:10:00Z",
    )
    assert script and len(script["sections"]) == 2
    _checkpoint_all_preceding(projects, project_id, project_dir, script, plan.to_dict())

    rendered = VerticalClipComposer().render_approved_batch(
        script=script, plan=plan, source_video_path=source,
        output_dir=project_dir / "renders", transcript_segments=transcript["transcript"],
        config=VerticalRenderConfig(burn_subtitles=True, subtitle_format="ass", highlight_style="none"),
    )
    assert rendered.succeeded_count == 2 and rendered.failed_count == 0
    assert all(clip.success and Path(clip.output_video_path).is_file() for clip in rendered.clips)

    black = tmp_path / "deliberate-black.mp4"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=1080x1920:r=25:d=2", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(black),
    ])
    render_results = [*rendered.clips, {
        "candidate_id": "bad-black", "video_path": str(black), "success": True,
        "duration_seconds": 2.0,
    }]
    qa = MediaQAInspector().inspect_batch(
        project_id=project_id, render_results=render_results, plan=plan,
        output_path=project_dir / "artifacts" / "final_review.json",
    )
    assert len(qa.passed_clip_ids) == 2 and qa.failed_clip_ids == ("bad-black",)
    assert qa.overall_status == "revise"
    validate_artifact("final_review", qa.final_review)
    assert MediaQAInspector.apply_qa_to_plan(plan, qa).candidates[0].production_state == "QA_PASSED"

    clips = []
    for rank, rendered_clip in enumerate(rendered.clips, start=1):
        clips.append({
            "clip_id": rendered_clip.candidate_id, "video_path": rendered_clip.output_video_path,
            "subtitles_path": rendered_clip.subtitle_path, "title": f"Moment {rank}",
            "description": "A source-grounded moment.", "hashtags": ["#learning"], "rank": rank,
        })
    clips.append({
        "clip_id": "bad-black", "video_path": str(black), "title": "Must not ship",
        "qa_error": "opening black frame detected", "rank": 3,
    })
    exported = ExportBundle().execute({
        "clips": clips, "final_review": qa.final_review, "export_dir": str(project_dir / "exports"),
        "project_name": project_id, "plan_sha256": rendered.plan_sha256,
        "timestamp": "2026-11-17T12:30:00+00:00",
    })
    assert exported.success, exported.error
    assert exported.data["exported_count"] == 2
    assert exported.data["skipped_failed_clips"] == ["bad-black"]
    export_root = Path(exported.data["export_path"])
    assert len(list((export_root / "clips").glob("01_*/video.mp4"))) == 1
    assert len(list((export_root / "clips").glob("02_*/video.mp4"))) == 1
    assert not list((export_root / "clips").glob("*bad-black*"))
    assert (export_root / "manifest.json").is_file()
    for clip_dir in (export_root / "clips").iterdir():
        assert (clip_dir / "video.mp4").is_file()
        assert (clip_dir / "subtitles.ass").is_file()
        assert (clip_dir / "metadata.json").is_file()
        assert (clip_dir / "description.txt").is_file()
    validate_artifact("publish_log", exported.data["publish_log"])
    statuses = [entry["status"] for entry in exported.data["publish_log"]["entries"]]
    assert statuses.count("exported") == 2 and statuses.count("failed") == 1

    reports = []
    for clip in rendered.clips:
        media = _probe(Path(clip.output_video_path))
        video_stream = next(s for s in media["streams"] if s["codec_type"] == "video")
        audio_stream = next(s for s in media["streams"] if s["codec_type"] == "audio")
        reports.append({
            "path": clip.output_video_path, "format": "mp4", "codec": video_stream["codec_name"],
            "audio_codec": audio_stream["codec_name"], "resolution": f'{video_stream["width"]}x{video_stream["height"]}',
            "fps": 25, "duration_seconds": clip.duration_seconds, "file_size_bytes": Path(clip.output_video_path).stat().st_size,
        })
    render_report = {"version": "1.0", "outputs": reports, "final_review_ref": "artifacts/final_review.json"}
    write_checkpoint(projects, project_id, "compose", "completed", {
        "render_report": render_report, "final_review": qa.final_review,
    }, pipeline_type="clip-factory", human_approved=True)
    publish_log = exported.data["publish_log"]
    write_checkpoint(projects, project_id, "publish", "awaiting_human", {"publish_log": publish_log},
                     pipeline_type="clip-factory", human_approved=False)
    write_checkpoint(projects, project_id, "publish", "completed", {"publish_log": publish_log},
                     pipeline_type="clip-factory", human_approved=True)
    board = load_board_state(project_dir)
    assert {"final_review", "publish_log", "clip_selection_plan", "script"}.issubset(board["artifacts"])
    publish_stage = next(stage for stage in board["stages"] if stage["name"] == "publish")
    assert publish_stage["gate_skipped"] is False
