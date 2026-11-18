"""Unit & integration tests for whole-system Studio BFF APIs (Stage A)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backlot import server as backlot_server
from studio.server import create_app
from studio.session_store import SessionStore
from studio.supervisor import SupervisorManager


FAKE_SUPERVISOR_SCRIPT = """
import json, sys
print(json.dumps({"type": "system", "subtype": "init", "session_id": "claude_fake_99", "model": "nim/qwen"}))
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Acknowledged production brief."}]}}))
print(json.dumps({"type": "result", "subtype": "success", "duration_ms": 42, "is_error": False}))
"""


@pytest.fixture
def studio_env(tmp_path: Path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "demo-proj"
    (proj / "artifacts").mkdir(parents=True)
    (proj / "history").mkdir(parents=True)
    (proj / "renders").mkdir(parents=True)

    (proj / "project.json").write_text(
        json.dumps({"project_id": "demo-proj", "pipeline_type": "animated-explainer"}),
        encoding="utf-8",
    )
    (proj / "artifacts" / "brief.json").write_text(
        json.dumps({"topic": "Black Holes", "duration_seconds": 60}),
        encoding="utf-8",
    )
    (proj / "history" / "checkpoint_proposal_001.json").write_text(
        json.dumps({"stage": "proposal", "status": "awaiting_human", "timestamp": "2026-11-18T10:00:00Z"}),
        encoding="utf-8",
    )

    # Generate a tiny real 1.5s mp4 with sine tone so waveform + filmstrip tests run end-to-end
    media_mp4 = proj / "renders" / "sample.mp4"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg, "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=0x1e293b:s=320x180:d=1.5:r=24",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                str(media_mp4),
            ],
            check=True,
            timeout=20,
        )

    fake_sup = tmp_path / "fake_sup.py"
    fake_sup.write_text(FAKE_SUPERVISOR_SCRIPT, encoding="utf-8")

    monkeypatch.setattr(backlot_server, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("backlot.state.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("studio.supervisor.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("studio.server.STUDIO_UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr("studio.media_engine.STUDIO_CACHE_DIR", tmp_path / "cache")

    store = SessionStore(tmp_path / "studio.sqlite")
    mgr = SupervisorManager(
        store,
        supervisor_args_prefix=[sys.executable, str(fake_sup)],
        cwd=tmp_path,
    )
    token = "test_bff_token_123456"
    app = create_app(store=store, supervisor=mgr, studio_token=token, enable_watcher=False)
    headers = {
        "Origin": "http://127.0.0.1:4760",
        "Sec-Fetch-Site": "same-origin",
        "X-Studio-Token": token,
    }
    with TestClient(app, base_url="http://127.0.0.1:4760") as client:
        yield client, headers, proj, media_mp4


def test_catalog_endpoints(studio_env):
    client, _, _, _ = studio_env

    pipes = client.get("/api/studio/pipelines")
    assert pipes.status_code == 200
    names = {p["name"] for p in pipes.json()}
    assert "clip-factory" in names
    assert "animated-explainer" in names
    assert len(names) >= 12

    playbooks = client.get("/api/studio/playbooks")
    assert playbooks.status_code == 200
    pb_list = playbooks.json()
    assert len(pb_list) >= 5
    assert "palette" in pb_list[0]

    profiles = client.get("/api/studio/media-profiles")
    assert profiles.status_code == 200
    prof_names = {p["name"] for p in profiles.json()}
    assert "youtube_shorts" in prof_names
    assert "youtube_landscape" in prof_names

    cfg = client.get("/api/studio/config")
    assert cfg.status_code == 200
    assert "budget" in cfg.json()

    music = client.get("/api/studio/music-library")
    assert music.status_code == 200
    assert "tracks" in music.json()

    tools = client.get("/api/studio/tools")
    assert tools.status_code == 200
    tdata = tools.json()
    assert tdata["total"] >= 100
    assert "counts" in tdata
    assert "capabilities" in tdata


def test_fonts_and_path_jail(studio_env):
    client, _, _, _ = studio_env
    r = client.get("/fonts/Montserrat-Bold.ttf")
    assert r.status_code == 200
    assert len(r.content) > 1000

    bad = client.get("/fonts/../../secret.txt")
    assert bad.status_code in (400, 403, 404)


def test_project_deep_inspection_and_nle_media(studio_env):
    client, _, _, media_mp4 = studio_env

    art = client.get("/api/studio/project/demo-proj/artifacts/brief")
    assert art.status_code == 200
    assert art.json()["data"]["topic"] == "Black Holes"

    hist = client.get("/api/studio/project/demo-proj/history")
    assert hist.status_code == 200
    assert "proposal" in hist.json()["stages"]

    files = client.get("/api/studio/project/demo-proj/files")
    assert files.status_code == 200
    assert any(f["name"] == "brief.json" for f in files.json()["files"])

    if media_mp4.is_file():
        wf = client.get("/api/studio/project/demo-proj/waveform/renders/sample.mp4?bins=64")
        assert wf.status_code == 200
        wf_data = wf.json()
        assert wf_data["has_audio"] is True
        assert len(wf_data["peaks"]) == 64
        assert max(wf_data["peaks"]) > 0.5

        fs = client.get("/api/studio/project/demo-proj/filmstrip/renders/sample.mp4?count=6&w=120")
        assert fs.status_code == 200
        fs_data = fs.json()
        assert len(fs_data["frames"]) >= 4
        frame_url = fs_data["frames"][0]["url"]
        img = client.get(frame_url)
        assert img.status_code == 200
        assert img.headers["content-type"].startswith("image/jpeg")


def test_upload_security_and_streaming(studio_env):
    client, headers, _, _ = studio_env

    # Missing CSRF token -> 403
    unauth = client.post("/api/studio/upload?filename=clip.mp4", content=b"12345")
    assert unauth.status_code == 403

    # Disallowed extension -> 400
    bad_ext = client.post(
        "/api/studio/upload?filename=evil.exe",
        content=b"MZ...",
        headers=headers,
    )
    assert bad_ext.status_code == 400

    # Valid upload -> 201
    ok = client.post(
        "/api/studio/upload?filename=my_podcast.mp4",
        content=b"\x00\x00\x00\x18ftypmp42",
        headers=headers,
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["ok"] is True
    assert Path(body["path"]).is_file()


def test_universal_production_session_and_gate_flow(studio_env):
    client, headers, _, _ = studio_env

    # Launch an animated-explainer production
    prod = client.post(
        "/api/studio/productions",
        json={
            "pipeline_type": "animated-explainer",
            "brief_prompt": "60s explainer about orbital mechanics",
            "project_id": "demo-proj",
            "style_playbook": "clean-professional",
            "media_profile": "youtube_landscape",
            "budget_usd": 3.0,
        },
        headers=headers,
    )
    assert prod.status_code == 201
    sid = prod.json()["session_id"]

    # Create standalone attached session
    s2 = client.post(
        "/api/studio/sessions",
        json={"title": "Review Session", "project_id": "demo-proj"},
        headers=headers,
    )
    assert s2.status_code == 201
    sid2 = s2.json()["session_id"]

    # Universal gate decision
    gate = client.post(
        f"/api/studio/sessions/{sid2}/gate",
        json={"stage": "proposal", "decision": "approve", "notes": "Looks great!"},
        headers=headers,
    )
    assert gate.status_code == 202

    # Delete session
    deleted = client.delete(f"/api/studio/sessions/{sid}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_fs_browse_returns_valid_listing(studio_env):
    client, _, _, _ = studio_env
    res = client.get("/api/studio/fs/browse")
    assert res.status_code == 200
    data = res.json()
    assert "path" in data
    assert isinstance(data["dirs"], list)
    assert isinstance(data["files"], list)


def test_creator_editor_draft_brand_kit_subtitles_and_title_override(studio_env):
    client, headers, proj_dir, _ = studio_env

    # Fonts catalog lists bundled DirectWrite fonts
    fonts = client.get("/api/studio/fonts")
    assert fonts.status_code == 200
    assert any("Montserrat" in f["filename"] for f in fonts.json())

    # Editor draft + title override persistence (outside projects/)
    no_csrf = client.put("/api/studio/project/demo-proj/editor-draft", json={"draft": {"aspect": "9:16"}})
    assert no_csrf.status_code == 403

    saved = client.put(
        "/api/studio/project/demo-proj/editor-draft",
        json={"draft": {"aspect_ratio": "9:16", "captions": [{"id": "c1", "start": 0, "end": 2, "text": "Hello"}]}},
        headers=headers,
    )
    assert saved.status_code == 200
    got = client.get("/api/studio/project/demo-proj/editor-draft")
    assert got.status_code == 200
    assert got.json()["draft"]["aspect_ratio"] == "9:16"

    # Provisional crop draft saved in exact reframe_v2 center-point contract
    cd = client.put(
        "/api/studio/project/demo-proj/crop-draft/clip_01",
        json={"overrides": {"0": {"x": 0.42}, "1": {"top": {"x": 0.28, "y": 0.45}, "bottom": {"x": 0.72, "y": 0.45}}}},
        headers=headers,
    )
    assert cd.status_code == 200

    # Title override reflects in /state without mutating projects/demo-proj/project.json
    rn = client.patch(
        "/api/studio/project/demo-proj/title",
        json={"title": "Renamed Creator Episode"},
        headers=headers,
    )
    assert rn.status_code == 200
    st = client.get("/api/studio/project/demo-proj/state")
    assert st.status_code == 200
    assert st.json()["title"] == "Renamed Creator Episode"
    assert st.json()["crop_drafts"]["clip_01"]["0"]["x"] == 0.42

    # Subtitles generate & read from project transcript.json
    (proj_dir / "source").mkdir(parents=True, exist_ok=True)
    (proj_dir / "source" / "transcript.json").write_text(
        json.dumps({
            "segments": [
                {
                    "start": 0.0,
                    "end": 3.0,
                    "speaker": "Host",
                    "words": [
                        {"word": "Kabhi-kabhi", "start": 0.0, "end": 0.6},
                        {"word": "hum", "start": 0.6, "end": 1.0},
                        {"word": "kisi", "start": 1.0, "end": 1.4},
                        {"word": "book", "start": 1.4, "end": 1.9},
                        {"word": "padte", "start": 1.9, "end": 2.5},
                    ],
                }
            ]
        }),
        encoding="utf-8",
    )
    gen = client.post(
        "/api/studio/project/demo-proj/subtitles/generate",
        json={"candidate_id": "source", "language": "hi-EN", "max_words": 4},
        headers=headers,
    )
    assert gen.status_code == 200
    gdata = gen.json()
    assert gdata["status"] == "ready"
    assert gdata["evidence_quality"] == "medium_word"
    assert len(gdata["captions"]) == 2
    assert gdata["captions"][0]["text"] == "Kabhi-kabhi hum kisi book"

    # Brand Kit CRUD (CSRF-protected)
    bk_add = client.post(
        "/api/studio/brand-kit",
        json={"category": "saved", "name": "Hinglish Pop Caption", "payload": {"preset": "hinglish_impact"}},
        headers=headers,
    )
    assert bk_add.status_code == 201
    iid = bk_add.json()["item_id"]
    bk_list = client.get("/api/studio/brand-kit?category=saved")
    assert bk_list.status_code == 200
    assert any(x["item_id"] == iid for x in bk_list.json()["items"])
    bk_del = client.delete(f"/api/studio/brand-kit/{iid}", headers=headers)
    assert bk_del.status_code == 200

    # Tool action directive + proposal runtime lock + style corrections
    s = client.post(
        "/api/studio/sessions",
        json={"title": "Creator Session", "project_id": "demo-proj"},
        headers=headers,
    ).json()
    sid = s["session_id"]
    ta = client.post(
        f"/api/studio/sessions/{sid}/tool-action",
        json={"action": "silence_cutter", "params": {"threshold_db": -35}, "project_id": "demo-proj"},
        headers=headers,
    )
    assert ta.status_code == 202
