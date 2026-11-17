"""Real FFmpeg proof for approved vertical clip production and batch resilience."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lib.models.clip_plan import ClipSelectionPlan
from tools.analysis.clip_selector import (
    ClipSelector,
    build_script_from_plan,
    finalize_approved_selection,
)
from tools.base_tool import ToolResult
from tools.video.video_trimmer import VideoTrimmer
from lib.vertical_composer import VerticalClipComposer, VerticalRenderConfig


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg and ffprobe required"
)


def _run(command):
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True, timeout=180)


def _make_source(path: Path):
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        "color=c=red:size=1280x720:rate=10:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
        "-vf", r"drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable=gte(t\,3)",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ])


def _approved_artifacts(project_id="m4-project"):
    english = "We learned this lesson the hard way."
    hindi = "यह सच में काम करता है।"
    segments = [
        {"text": english, "start": 1.0, "duration": 2.0},
        {"text": hindi, "start": 3.0, "duration": 2.0},
    ]
    result = ClipSelector().execute({
        "project_id": project_id, "source_media_ref": "master.mp4", "transcript": {"transcript": segments},
        "transcript_format": "youtube", "min_duration_seconds": 1.0,
        "candidates": [{
            "candidate_id": "clip-one", "start_seconds": 1.0, "end_seconds": 5.0,
            "original_spoken_dialogue": f"{english} {hindi}", "spoken_opening": english,
            "spoken_hook_text": english, "editorial_title": "The lesson",
            "cold_viewer_audit": {
                "subject_grounded": True, "entities_resolved": True, "pronouns_resolved": True,
                "premise_to_payoff_complete": True, "qualifiers_preserved": True, "passed": True,
            },
            "editorial_scores": [{"dimension": "hook_pull", "rationale": "Specific source-grounded opening.", "score": .9}],
        }],
        "generated_at": "2026-11-17T12:00:00Z",
    })
    assert result.success, result.error
    plan, script, _ = finalize_approved_selection(
        result.data["plan"],
        [{"candidate_id": "clip-one", "action": "approve", "review_metadata": "Owner approved."}],
        reviewed_at="2026-11-17T12:30:00Z",
    )
    assert script is not None
    return plan, script, segments


def _probe(path):
    return json.loads(_run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ]).stdout)


def test_approved_clip_trims_reframes_burns_rebased_multilingual_ass(tmp_path):
    master = tmp_path / "master.mp4"
    proxy = tmp_path / "proxy.mp4"
    _make_source(master)
    shutil.copy2(master, proxy)
    master_hash = hashlib.sha256(master.read_bytes()).hexdigest()
    plan, script, transcript = _approved_artifacts()

    collision = VerticalClipComposer().render_clip(
        candidate_id="master", source_video_path=master, start_seconds=1.0, end_seconds=2.0,
        output_dir=tmp_path,
    )
    assert not collision.success and "overwrite" in collision.error
    assert hashlib.sha256(master.read_bytes()).hexdigest() == master_hash

    blocked_dir = tmp_path / "blocked-output"
    provisional = dict(script, metadata=dict(script["metadata"], approval_status="provisional"))
    with pytest.raises(ValueError, match="not approved"):
        VerticalClipComposer().render_approved_batch(
            script=provisional, plan=plan, source_video_path=master, output_dir=blocked_dir,
        )
    assert not blocked_dir.exists()
    drifted = plan.model_copy(update={"source_media_ref": "different.mp4"})
    with pytest.raises(ValueError, match="SHA-256"):
        VerticalClipComposer().render_approved_batch(
            script=script, plan=drifted, source_video_path=master, output_dir=blocked_dir,
        )
    assert not blocked_dir.exists()

    output_dir = tmp_path / "renders"
    config = VerticalRenderConfig(burn_subtitles=True, subtitle_format="ass", highlight_style="karaoke")
    batch = VerticalClipComposer().render_approved_batch(
        script=script, plan=plan, source_video_path=master, output_dir=output_dir,
        transcript_segments=transcript, config=config, shot_cuts=[3.0],
        speaker_tracks=[{
            "timestamp_seconds": 2.0,
            "bbox": {"x": .35, "y": .2, "width": .15, "height": .3},
            "active": True, "speaker": "host",
        }],
        source_manifest={"proxy_video_path": str(proxy), "master_video_path": str(master)},
    )
    assert batch.succeeded_count == 1 and batch.failed_count == 0
    clip = batch.clips[0]
    assert clip.success, clip.error
    assert clip.source_video_used == str(proxy)
    assert clip.output_video_path and Path(clip.output_video_path).is_file()
    assert clip.subtitle_path and Path(clip.subtitle_path).is_file()
    assert hashlib.sha256(master.read_bytes()).hexdigest() == master_hash
    assert not list(output_dir.glob(".clip-one-*"))

    streams = _probe(Path(clip.output_video_path))
    video = next(stream for stream in streams["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in streams["streams"] if stream["codec_type"] == "audio")
    assert (video["width"], video["height"]) == (1080, 1920)
    assert (video["codec_name"], video["pix_fmt"]) == ("h264", "yuv420p")
    assert audio["codec_name"] == "aac"
    assert float(streams["format"]["duration"]) == pytest.approx(4.0, abs=.35)

    ass_text = Path(clip.subtitle_path).read_text(encoding="utf-8")
    assert "यह सच में काम करता है" in ass_text
    dialogue_rows = [row for row in ass_text.splitlines() if row.startswith("Dialogue:")]
    assert dialogue_rows
    assert "0:00:00.00" in ass_text and "0:00:04.00" in ass_text
    assert "0:00:01.00" not in ass_text


def test_batch_continues_after_one_trimmer_failure(tmp_path):
    source = tmp_path / "source.mp4"
    _make_source(source)
    plan, _, _ = _approved_artifacts("batch-test")
    original = plan.candidates[0]
    second = original.model_copy(update={
        "candidate_id": "clip-two", "start_seconds": 2.0, "end_seconds": 4.0,
        "duration_seconds": 2.0, "editorial_title": "Second clip",
    })
    expanded_plan = plan.model_copy(update={"candidates": (original, second)})
    # Validated generated script will include only approved clips. Mark second with explicit review evidence.
    second = second.model_copy(update={
        "review_state": "HUMAN_APPROVED", "human_reviewed_at": "2026-11-17T12:30:00Z",
        "review_metadata": "Approved for resilience test.",
    })
    expanded_plan = plan.model_copy(update={"candidates": (original, second)})
    script = build_script_from_plan(expanded_plan, approval_status="approved")
    assert script is not None and len(script["sections"]) == 2

    class FailFirstTrimmer:
        def __init__(self):
            self.delegate = VideoTrimmer()

        def execute(self, inputs):
            if inputs["start_seconds"] == 1.0:
                return ToolResult(success=False, error="injected first clip trimmer failure")
            return self.delegate.execute(inputs)

    batch = VerticalClipComposer(trimmer=FailFirstTrimmer()).render_approved_batch(
        script=script, plan=expanded_plan, source_video_path=source, output_dir=tmp_path / "batch-renders",
        config=VerticalRenderConfig(burn_subtitles=False),
    )
    assert (batch.succeeded_count, batch.failed_count) == (1, 1)
    assert batch.clips[0].success is False
    assert "injected first clip" in batch.clips[0].error
    assert batch.clips[1].success is True, batch.clips[1].error
    assert Path(batch.clips[1].output_video_path).is_file()
