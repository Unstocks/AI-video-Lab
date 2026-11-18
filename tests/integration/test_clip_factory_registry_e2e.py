"""Registry boundary test for local intake, vertical composition, QA and export."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from backlot.state import load_board_state
from lib.checkpoint import init_project, write_checkpoint
from tools.tool_registry import ToolRegistry
from tools.analysis.clip_selector import finalize_approved_selection


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")


def _run(command):
    subprocess.run(command, check=True, capture_output=True, timeout=90)


def test_pipeline_tools_are_registered_and_declared():
    registry = ToolRegistry()
    registry.discover()
    for name in ("local_media_intake", "media_qa", "vertical_clip_composer", "export_bundle"):
        assert registry.get(name) is not None, name
    for manifest_path in (Path("pipeline_defs/clip-factory.yaml"), Path("pipeline_defs/podcast-repurpose.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        compose = next(stage for stage in manifest["stages"] if stage["name"] == "compose")
        assert "media_qa" in compose["tools_available"]
        assert "vertical_clip_composer" in compose["tools_available"]


def test_registry_local_intake_to_render_qa_and_fail_closed_export(tmp_path, monkeypatch):
    import tools.analysis.local_media_intake as local_module
    from lib.url_ingest import URLIntakeAdapter

    registry = ToolRegistry()
    registry.discover()
    source = tmp_path / "source.mp4"
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=3",
        "-f", "lavfi", "-i", "aevalsrc=0.25*sin(2*PI*440*t)*(0.2+0.8*abs(sin(2*PI*0.7*t))):s=48000:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
    ])
    monkeypatch.setattr(local_module, "URLIntakeAdapter", lambda pipeline_type: URLIntakeAdapter(
        projects_dir=tmp_path / "projects", pipeline_type=pipeline_type))
    intake = registry.get("local_media_intake").execute({
        "local_path": str(source), "project_id": "registry-e2e", "pipeline_type": "clip-factory",
    })
    assert intake.success, intake.error
    manifest_path = intake.data["manifest_path"]
    projects_dir = tmp_path / "projects"
    project = init_project("registry-e2e", title="Registry E2E", pipeline_type="clip-factory", pipeline_dir=projects_dir)
    brief = {
        "version": "1.0", "title": "One useful lesson", "hook": "Measure before changing the product.",
        "key_points": ["Measure first"], "tone": "clear", "style": "clean-professional",
        "target_platform": "generic", "target_duration_seconds": 30,
    }
    write_checkpoint(projects_dir, "registry-e2e", "idea", "completed", {"brief": brief},
                     pipeline_type="clip-factory", human_approved=True)
    transcript = {"transcript": [{"text": "We measured the problem before changing the product.", "start": 0, "duration": 3}]}
    selection = registry.get("clip_selector").execute({
        "project_id": "registry-e2e", "source_media_ref": intake.data["video_path"],
        "transcript": transcript, "transcript_format": "youtube", "min_duration_seconds": 1,
        "max_duration_seconds": 4, "preferred_max_duration_seconds": 3,
        "output_dir": str(project / "artifacts"), "generated_at": "2026-11-18T00:00:00Z",
        "candidates": [{
            "candidate_id": "lesson", "start_seconds": 0, "end_seconds": 3,
            "original_spoken_dialogue": "We measured the problem before changing the product.",
            "spoken_opening": "We measured the problem", "spoken_hook_text": "We measured the problem",
            "editorial_title": "Measure first", "cold_viewer_audit": {
                "subject_grounded": True, "entities_resolved": True, "pronouns_resolved": True,
                "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": True,
            }, "editorial_scores": [{"dimension": "hook_pull", "score": .9, "rationale": "Specific and grounded."}],
        }],
    })
    assert selection.success, selection.error
    write_checkpoint(projects_dir, "registry-e2e", "script", "awaiting_human", {
        "script": selection.data["provisional_script"], "clip_selection_plan": selection.data["plan"],
    }, pipeline_type="clip-factory", human_approved=False)
    plan, script, _ = finalize_approved_selection(selection.data["plan"], [
        {"candidate_id": "lesson", "action": "approve", "review_metadata": "Reviewed."},
    ], reviewed_at="2026-11-18T00:00:00Z", output_dir=project / "artifacts")
    write_checkpoint(projects_dir, "registry-e2e", "script", "completed", {
        "script": script, "clip_selection_plan": plan.to_dict(),
    }, pipeline_type="clip-factory", human_approved=True)
    rendered = registry.get("vertical_clip_composer").execute({
        "mode": "approved_batch", "script": script, "plan": plan.to_dict(),
        "source_video_path": intake.data["video_path"], "source_manifest": manifest_path,
        "output_dir": str(project / "renders" / "clips"), "config": {"burn_subtitles": False},
    })
    assert rendered.success, rendered.error
    render_rows = [{**clip, "duration_seconds": clip["duration_seconds"], "locked_runtime": "ffmpeg"}
                   for clip in rendered.data["clips"]]
    review = registry.get("media_qa").execute({
        "mode": "batch", "project_id": "registry-e2e", "render_results": render_rows,
        "plan": plan.to_dict(), "output_path": str(project / "artifacts" / "final_review.json"),
    })
    assert review.success, review.error
    clip = rendered.data["clips"][0]
    write_checkpoint(projects_dir, "registry-e2e", "compose", "in_progress", {
        "render_report": {
            "version": "1.0", "outputs": [{
                "path": clip["output_video_path"], "format": "mp4", "codec": "h264",
                "resolution": "1080x1920", "duration_seconds": clip["duration_seconds"],
            }], "final_review_ref": str(project / "artifacts" / "final_review.json"),
        },
        "final_review": review.data["final_review"],
    }, pipeline_type="clip-factory")
    exported = registry.get("export_bundle").execute({
        "clips": [{"clip_id": "lesson", "video_path": rendered.data["clips"][0]["output_video_path"]}],
        "final_review": review.data["final_review"], "clip_selection_plan": plan.to_dict(),
        "script": script, "plan_sha256": plan.compute_plan_sha256(),
        "export_dir": str(project / "exports"),
    })
    assert exported.success, exported.error
    mp4 = Path(exported.artifacts[0])
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True, timeout=20,
    ).stdout)
    video_stream = next(stream for stream in probe["streams"] if stream["codec_type"] == "video")
    assert (video_stream["codec_name"], video_stream["width"], video_stream["height"], video_stream["pix_fmt"]) == ("h264", 1080, 1920, "yuv420p")
    board = load_board_state(project)
    stage_names = {stage["name"] for stage in board["stages"]}
    assert {"idea", "script", "scene_plan", "assets", "edit", "compose", "publish"} <= stage_names
    assert board["artifacts"]["clip_selection_plan"]["version"] == "1.0"
    assert board["artifacts"]["final_review"]["status"] == "pass"
    assert any(item["path"].startswith("renders\\clips\\") or item["path"].startswith("renders/clips/")
               for item in board["media"]["renders"])
