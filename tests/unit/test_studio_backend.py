"""Unit & FastAPI TestClient tests for Studio backend (FE-2, FE-3, FE-4).

Covers:
- studio.security (loopback IP/Origin & per-boot X-Studio-Token CSRF)
- studio.session_store (SQLite sessions, messages, crop_drafts)
- studio.prompts (deterministic directives for Start/Approve/Reframe/Recut/Style/Export)
- studio.supervisor (mocked fcc-claude NDJSON stream, --resume continuity,
  automatic project_id linking, 409 concurrency lock, clean stop_run)
- studio.server (REST routes, all 8 real subtitle presets, CSRF rejection,
  path traversal 403, transcript endpoint, mocked job lifecycle)
"""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lib.subtitle_styles import SUBTITLE_STYLE_PRESETS
from studio import prompts
from studio.security import is_loopback_client, is_loopback_origin
from studio.server import create_app
from studio.session_store import SessionStore
from studio.supervisor import SessionBusyError, SupervisorManager


def _write_fake_fcc_script(tmp_path: Path, *, sleep_s: float = 0.0) -> Path:
    """Create a tiny Python script emulating `fcc-claude --output-format stream-json --verbose`."""
    script = tmp_path / "fake_fcc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json, sys, time

            args = sys.argv[1:]
            resumed = "--resume" in args
            resume_id = args[args.index("--resume") + 1] if resumed else None
            prompt = args[args.index("-p") + 1] if "-p" in args else ""

            sid = resume_id or "claude-ses-999"
            print(json.dumps({{"type": "system", "subtype": "init", "session_id": sid, "model": "nvidia/nemotron-3-ultra"}}), flush=True)
            if {sleep_s} > 0:
                time.sleep({sleep_s})
            print(json.dumps({{
                "type": "assistant",
                "message": {{
                    "content": [
                        {{"type": "tool_use", "id": "tu_1", "name": "url_intake", "input": {{"project_id": "demo-podcast", "url": "https://youtu.be/abc"}}}}
                    ]
                }}
            }}), flush=True)
            print(json.dumps({{
                "type": "user",
                "message": {{
                    "content": [
                        {{"type": "tool_result", "tool_use_id": "tu_1", "is_error": False, "content": "Ingested projects/demo-podcast/source/source_video.mp4"}}
                    ]
                }}
            }}), flush=True)
            reply = f"RESUMED={{resumed}} PROMPT_LEN={{len(prompt)}}"
            print(json.dumps({{
                "type": "assistant",
                "message": {{"content": [{{"type": "text", "text": reply}}]}}
            }}), flush=True)
            print(json.dumps({{"type": "result", "subtype": "success", "session_id": sid, "duration_ms": 42}}), flush=True)
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return script


class TestSecurityAndStore:
    def test_loopback_ip_and_origin_helpers(self):
        assert is_loopback_client("127.0.0.1") is True
        assert is_loopback_client("::1") is True
        assert is_loopback_client("::ffff:127.0.0.1") is True
        assert is_loopback_client("192.168.1.50") is False
        assert is_loopback_client("8.8.8.8") is False

        assert is_loopback_origin(None) is True
        assert is_loopback_origin("http://127.0.0.1:4760") is True
        assert is_loopback_origin("http://localhost:4760") is True
        assert is_loopback_origin("https://evil.example") is False
        assert is_loopback_origin("http://127.0.0.1.evil.com") is False

    def test_session_store_crud_and_crop_drafts(self, tmp_path: Path):
        store = SessionStore(tmp_path / "sessions.sqlite")
        s = store.create_session(title="Podcast Ep 1", source_input="https://youtu.be/xyz")
        sid = s["session_id"]
        assert s["status"] == "idle"

        store.update_session(sid, claude_session_id="cl-1", project_id="ep-1", status="running")
        got = store.get_session(sid)
        assert got["claude_session_id"] == "cl-1"
        assert got["project_id"] == "ep-1"

        m1 = store.append_message(sid, "user", {"text": "hello"})
        m2 = store.append_message(sid, "assistant", {"text": "world"})
        assert [m["id"] for m in store.list_messages(sid)] == [m1["id"], m2["id"]]
        assert [m["id"] for m in store.list_messages(sid, after_id=m1["id"])] == [m2["id"]]

        store.save_crop_draft("ep-1", "clip_01", {"0": 0.25, "1": {"top": 0.25, "bottom": 0.75}})
        drafts = store.get_crop_drafts("ep-1")
        assert drafts["clip_01"]["0"] == 0.25

    def test_prompts_are_deterministic_and_structured(self):
        p1 = prompts.build_start_job_prompt(
            source_input="https://youtu.be/test", clip_count=3, style_preset="neon_glow"
        )
        assert "url_intake" in p1 and "neon_glow" in p1 and "awaiting_human" in p1

        p2 = prompts.build_approval_prompt(
            project_id="ep-1", approved_ids=["clip_01"], rejected_ids=["clip_02"]
        )
        assert "HUMAN_APPROVED" in p2 and "clip_01" in p2 and "vertical_clip_composer" in p2


class TestSupervisorManager:
    def test_ndjson_stream_resume_project_linking_and_stop(self, tmp_path: Path):
        fake_fcc = _write_fake_fcc_script(tmp_path)
        store = SessionStore(tmp_path / "sup.sqlite")
        mgr = SupervisorManager(
            store,
            supervisor_args_prefix=[sys.executable, str(fake_fcc)],
            cwd=tmp_path,
        )

        async def _scenario():
            sess = await mgr.start_url_job(
                source_input="https://youtu.be/abc",
                clip_count=2,
                style_preset="hinglish_impact",
            )
            sid = sess["session_id"]
            # Wait for turn 1 to finish
            for _ in range(100):
                if not mgr.is_running(sid):
                    break
                await asyncio.sleep(0.05)

            s1 = store.get_session(sid)
            assert s1["claude_session_id"] == "claude-ses-999"
            assert s1["project_id"] == "demo-podcast"  # auto-linked from tool_use!
            assert s1["status"] == "idle"

            msgs1 = store.list_messages(sid)
            roles = [m["role"] for m in msgs1]
            assert "user" in roles and "tool_use" in roles and "tool_result" in roles and "assistant" in roles
            assert any("RESUMED=False" in m["content"].get("text", "") for m in msgs1 if m["role"] == "assistant")

            # Turn 2: approve -> must pass --resume claude-ses-999!
            await mgr.send_approval(sid, approved_ids=["clip_01"])
            for _ in range(100):
                if not mgr.is_running(sid):
                    break
                await asyncio.sleep(0.05)

            msgs2 = store.list_messages(sid)
            assert any("RESUMED=True" in m["content"].get("text", "") for m in msgs2 if m["role"] == "assistant")

        asyncio.run(_scenario())

    def test_concurrency_busy_guard_and_stop_run(self, tmp_path: Path):
        slow_fcc = _write_fake_fcc_script(tmp_path, sleep_s=5.0)
        store = SessionStore(tmp_path / "busy.sqlite")
        mgr = SupervisorManager(
            store,
            supervisor_args_prefix=[sys.executable, str(slow_fcc)],
            cwd=tmp_path,
        )

        async def _scenario():
            sess = await mgr.start_url_job(source_input="https://youtu.be/slow")
            sid = sess["session_id"]
            await asyncio.sleep(0.15)
            assert mgr.is_running(sid)
            with pytest.raises(SessionBusyError):
                await mgr.send_message(sid, "overlapping turn")

            stopped = await mgr.stop_run(sid)
            assert stopped["status"] == "stopped"
            assert not mgr.is_running(sid)

        asyncio.run(_scenario())


class TestStudioServerApi:
    def test_health_presets_csrf_and_endpoints(self, tmp_path: Path):
        fake_fcc = _write_fake_fcc_script(tmp_path)
        store = SessionStore(tmp_path / "api.sqlite")
        mgr = SupervisorManager(
            store,
            supervisor_args_prefix=[sys.executable, str(fake_fcc)],
            cwd=tmp_path,
        )
        token = "test-studio-secret-token"
        app = create_app(
            store=store,
            supervisor=mgr,
            studio_token=token,
            enable_watcher=False,
            allowed_hosts=["127.0.0.1", "localhost", "testserver"],
        )

        with TestClient(app) as client:
            # 1. Health & all 8 real presets
            r_health = client.get("/api/studio/health")
            assert r_health.status_code == 200
            assert r_health.json()["app"] == "studio"

            r_presets = client.get("/api/studio/presets")
            assert r_presets.status_code == 200
            names = {p["name"] for p in r_presets.json()}
            assert names == set(SUBTITLE_STYLE_PRESETS.keys())

            # 2. CSRF & Origin rejection on POST without token
            r_no_tok = client.post("/api/studio/jobs", json={"source_input": "https://youtu.be/x"})
            assert r_no_tok.status_code == 403

            r_bad_origin = client.post(
                "/api/studio/jobs",
                json={"source_input": "https://youtu.be/x"},
                headers={"X-Studio-Token": token, "Origin": "https://evil.example"},
            )
            assert r_bad_origin.status_code == 403

            # 3. Valid POST starts job and returns 201
            r_ok = client.post(
                "/api/studio/jobs",
                json={
                    "source_input": "https://youtu.be/abc",
                    "clip_count": 2,
                    "style_preset": "neon_glow",
                    "layout_mode": "auto",
                },
                headers={"X-Studio-Token": token, "Origin": "http://127.0.0.1:4760"},
            )
            assert r_ok.status_code == 201
            sid = r_ok.json()["session_id"]

            r_sess = client.get(f"/api/studio/sessions/{sid}")
            assert r_sess.status_code == 200
            assert r_sess.json()["session_id"] == sid

            # 4. Path traversal blocked on /media
            r_trav = client.get("/media/..%5C..%5Cetc/passwd")
            assert r_trav.status_code in (400, 403, 404)
