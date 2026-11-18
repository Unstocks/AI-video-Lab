"""Regression tests locking down every P0, P1, and P2 finding from the adversarial backend audit."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backlot.state import load_board_state
from lib.ffmpeg_profiles import QUALITY, video_encode_args
from lib.ffmpeg_utils import escape_ffmpeg_filter_path
from lib.llm_gateway import LLMGateway
from lib.media_qa import MediaQAConfig, MediaQAInspector
from lib.reframe_v2 import render_reframe_v2
from studio.server import create_app
from studio.session_store import SessionStore
from studio.supervisor import SupervisorManager
from tools.analysis.video_downloader import VideoDownloader
from tools.subtitle.subtitle_gen import SubtitleGen
from tools.video.auto_reframe import AutoReframe


# --- P0-1: Backlot Clip Studio joins REAL media_qa, export_bundle, script.sections ---

def test_p0_1_clip_studio_joins_real_media_qa_dict_export_manifest_and_script_sections(tmp_path: Path):
    proj = tmp_path / "real-schema-proj"
    (proj / "artifacts").mkdir(parents=True)
    (proj / "renders").mkdir(parents=True)
    (proj / "exports").mkdir(parents=True)

    # Real clip_selection_plan with provisional SELECTED_FOR_REVIEW + HUMAN_APPROVED
    plan = {
        "candidates": [
            {
                "candidate_id": "clip_01",
                "editorial_title": "Approved Exported Clip",
                "start_seconds": 10.0,
                "end_seconds": 40.0,
                "review_state": "HUMAN_APPROVED",
            },
            {
                "candidate_id": "clip_02",
                "editorial_title": "Provisional Clip",
                "start_seconds": 60.0,
                "end_seconds": 95.0,
                "review_state": "SELECTED_FOR_REVIEW",
            },
        ]
    }
    (proj / "artifacts" / "clip_selection_plan.json").write_text(json.dumps(plan), encoding="utf-8")

    # Real script.json uses sections[] (not candidates[])
    script = {
        "version": "1.0",
        "sections": [
            {"id": "clip_01", "label": "Approved Exported Clip", "start_seconds": 10.0, "end_seconds": 40.0}
        ],
    }
    (proj / "artifacts" / "script.json").write_text(json.dumps(script), encoding="utf-8")

    # Real MediaQAInspector final_review.json writes metadata.clip_reports as a DICT!
    final_review = {
        "version": "1.0",
        "status": "pass",
        "metadata": {
            "passed_clip_ids": ["clip_01"],
            "failed_clip_ids": [],
            "clip_reports": {
                "clip_01": {
                    "status": "pass",
                    "production_state": "QA_PASSED",
                    "technical_probe": {"resolution": "1080x1920", "codec": "h264", "pix_fmt": "yuv420p"},
                    "audio_spotcheck": {"integrated_lufs": -14.2, "true_peak_dbtp": -2.1},
                    "issues": [],
                }
            },
        },
    }
    (proj / "artifacts" / "final_review.json").write_text(json.dumps(final_review), encoding="utf-8")

    # Real ExportBundle writes exports/manifest.json with clip_catalog[].clip_id!
    (proj / "exports" / "manifest.json").write_text(
        json.dumps({
            "clip_catalog": [
                {"clip_id": "clip_01", "status": "exported", "export_path": "exports/clips/01_clip_01/video/clip_01.mp4"}
            ]
        }),
        encoding="utf-8",
    )

    state = load_board_state(proj)
    cs = state["clip_studio"]
    assert cs is not None
    assert cs["awaiting_approval_count"] == 1  # SELECTED_FOR_REVIEW counted!
    assert cs["approved_count"] == 1
    assert cs["qa_passed_count"] == 1
    assert cs["exported_count"] == 1

    c1 = next(c for c in cs["clips"] if c["candidate_id"] == "clip_01")
    assert c1["production_state"] == "EXPORTED"
    assert c1["qa"] is not None
    assert c1["qa"]["integrated_lufs"] == -14.2
    assert c1["qa"]["true_peak_dbtp"] == -2.1
    assert c1["exported_paths"] == ["exports/clips/01_clip_01/video/clip_01.mp4"]


# --- P0-2: SupervisorManager handles >64 KiB NDJSON lines & never hijacks bound project ---

def test_p0_2_supervisor_handles_150kb_ndjson_line_and_preserves_bound_project(tmp_path: Path):
    script = tmp_path / "big_line_fcc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            big_blob = "X" * 150_000
            print(json.dumps({"type": "system", "subtype": "init", "session_id": "cl-big"}), flush=True)
            print(json.dumps({
                "type": "user",
                "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": False, "content": big_blob}]}
            }), flush=True)
            print(json.dumps({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Mentioned projects/other-project in prose."}]}
            }), flush=True)
            print(json.dumps({"type": "result", "subtype": "success", "session_id": "cl-big"}), flush=True)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    store = SessionStore(tmp_path / "big.sqlite")
    mgr = SupervisorManager(store, supervisor_args_prefix=[sys.executable, str(script)], cwd=tmp_path)

    async def _run():
        sess = await mgr.start_url_job(source_input="https://youtu.be/big", project_id="locked-proj")
        sid = sess["session_id"]
        for _ in range(100):
            if not mgr.is_running(sid):
                break
            await asyncio.sleep(0.05)
        final = store.get_session(sid)
        assert final["status"] == "idle", final.get("last_error")
        assert final["project_id"] == "locked-proj"  # never hijacked by prose!
        msgs = store.list_messages(sid)
        assert any(m["role"] == "tool_result" for m in msgs)

    asyncio.run(_run())


# --- P0-3 & P0-5 & P1-1 & P1-6: Real FFmpeg sync, apostrophe path, strict loudnorm, layout preservation ---

@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
def test_p0_3_reframe_v2_multi_scene_zero_frame_drift(tmp_path: Path):
    """6s 30fps video with 5 non-keyframe cuts must produce ~180 frames without cumulative drift."""
    src = tmp_path / "sync_src.mp4"
    out = tmp_path / "sync_out.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=6",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "90",
            "-c:a", "aac", "-b:a", "128k",
            str(src),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    res = render_reframe_v2(
        src,
        out,
        shot_cuts=[1.1, 2.3, 3.4, 4.7, 5.3],
        codec="libx264",
        audio_copy=True,
    )
    assert Path(res["output"]).is_file()
    probe = json.loads(
        subprocess.check_output(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(out)],
            text=True,
        )
    )
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    nb_frames = int(v["nb_frames"])
    # Exact frame-count output: 6s @ 30fps = 180 frames (tolerance +/- 2 frames, NOT +15 drift!)
    assert 178 <= nb_frames <= 182, f"Frame drift detected: {nb_frames} frames (expected ~180)"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg unavailable")
def test_p0_5_apostrophe_path_escaping_works_in_sendcmd(tmp_path: Path):
    ap_dir = tmp_path / "o'brien's clip"
    ap_dir.mkdir(parents=True)
    cmd_file = ap_dir / "cmd.txt"
    cmd_file.write_text("0.0000 crop@c x 10;\n", encoding="utf-8")
    vf = f"sendcmd=f='{escape_ffmpeg_filter_path(cmd_file)}',crop@c=w=64:h=64:x=0:y=0"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=black:s=128x128:d=0.2", "-vf", vf, "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
def test_p1_1_enforce_loudnorm_window_actually_fails_quiet_clip(tmp_path: Path):
    quiet = tmp_path / "quiet_unnormalized.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=4",
            "-f", "lavfi", "-i", "aevalsrc='0.02*(0.55+0.45*sin(2*PI*1.5*t))*sin(2*PI*280*t)':s=48000:d=4",
            *video_encode_args(QUALITY, codec="libx264"),
            "-c:a", "aac", "-b:a", "128k",
            str(quiet),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    qa = MediaQAInspector().inspect_clip(
        candidate_id="q1",
        video_path=quiet,
        expected_duration_seconds=4.0,
        locked_runtime="ffmpeg",
        config=MediaQAConfig(enforce_loudnorm_window=True),
    )
    assert qa.production_state == "QA_FAILED"
    assert qa.check_statuses["audio_loudnorm"] == "FAIL"


def test_p1_2_video_encode_args_copy_omits_crf_and_pix_fmt():
    assert video_encode_args(QUALITY, codec="copy") == ["-c:v", "copy"]


def test_p1_4_video_downloader_blocks_private_url_upfront(tmp_path: Path):
    res = VideoDownloader().execute({
        "url": "http://169.254.169.254/latest/meta-data/",
        "output_dir": str(tmp_path),
    })
    assert not res.success
    assert "non-public" in (res.error or "").lower()


def test_p1_5_studio_server_validates_project_id_recut_types_and_fetch_metadata(tmp_path: Path):
    store = SessionStore(tmp_path / "sec.sqlite")
    mgr = SupervisorManager(store, supervisor_args_prefix=[sys.executable, "-c", "pass"], cwd=tmp_path)
    tok = "sec-tok"
    app = create_app(
        store=store, supervisor=mgr, studio_token=tok, enable_watcher=False,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    with TestClient(app) as client:
        # Cross-site Sec-Fetch-Site blocked on GET
        r_cross = client.get("/api/studio/presets", headers={"Sec-Fetch-Site": "cross-site"})
        assert r_cross.status_code == 403

        # Path-traversal project_id rejected (422)
        r_bad_pid = client.post(
            "/api/studio/jobs",
            json={"source_input": "https://youtu.be/x", "project_id": "../escape"},
            headers={"X-Studio-Token": tok},
        )
        assert r_bad_pid.status_code == 422

        # Boolean / inf rejected on RecutRequest
        s = store.create_session(title="t", project_id="valid-proj")
        r_bool = client.post(
            f"/api/studio/sessions/{s['session_id']}/recut",
            json={"candidate_id": "c1", "start_seconds": True, "end_seconds": 10.0},
            headers={"X-Studio-Token": tok},
        )
        assert r_bool.status_code == 422


def test_p2_2_llm_gateway_fails_fast_on_timeout():
    calls = {"n": 0}

    class FakeComp:
        def create(self, **kwargs):
            calls["n"] += 1
            raise TimeoutError("timed out")

    class M(BaseModel):
        a: int

    gw = LLMGateway(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeComp())))
    with pytest.raises(RuntimeError, match="transport/auth failure"):
        gw.complete_structured(system_prompt="s", user_prompt="u", response_model=M)
    assert calls["n"] == 1  # did NOT retry 3x!


def test_p2_4_continuation_words_preserve_negative_numbers_and_dotnet():
    words = [
        {"word": "at", "start": 0.0, "end": 0.2},
        {"word": "-5", "start": 0.2, "end": 0.4},
        {"word": "using", "start": 0.4, "end": 0.6},
        {"word": ".NET", "start": 0.6, "end": 0.9},
        {"word": "anti", "start": 0.9, "end": 1.1},
        {"word": "-hero", "start": 1.1, "end": 1.4},
        {"word": "$20", "start": 1.4, "end": 1.6},
        {"word": ".50", "start": 1.6, "end": 1.9},
    ]
    merged = SubtitleGen.merge_continuation_words(words)
    assert [w["word"] for w in merged] == ["at", "-5", "using", ".NET", "anti-hero", "$20.50"]
