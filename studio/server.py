"""AI Video Lab Studio — FastAPI server (127.0.0.1:4760).

Unified Top-Supervisor interactive cockpit:
- Reuses ``backlot.state`` for read-only project/clip state and Backlot's
  path-jailed HTTP 206 ``/media`` & cached ``/thumb`` handlers.
- Owns ``SupervisorManager`` (driving ``fcc-claude`` via stream-json & ``--resume``)
  and SQLite session persistence in ``.studio/sessions.sqlite``.
- Enforces hardened loopback-only + ``TrustedHostMiddleware`` + loopback ``Origin``
  + ``Sec-Fetch-Site`` + per-boot ``X-Studio-Token`` CSRF protection (TRAP-08).
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from backlot import server as backlot_server
from backlot.state import load_board_state
from lib.face_detector import MultiFaceDetector
from lib.ffmpeg_profiles import nvenc_available
from lib.subtitle_styles import SUBTITLE_STYLE_PRESETS, SubtitleStylePreset
from studio.security import (
    generate_studio_token,
    is_valid_project_id,
    require_loopback,
    require_studio_write,
)
from studio.session_store import SessionStore
from studio.supervisor import (
    SessionBusyError,
    SupervisorManager,
    SupervisorNotFoundError,
    discover_supervisor_bin,
    probe_fcc_health,
)

STUDIO_UI_DIR = Path(__file__).resolve().parent / "ui"
BACKLOT_UI_DIR = Path(__file__).resolve().parent.parent / "backlot" / "ui"
SSE_HEARTBEAT_SECONDS = 15
VALID_LAYOUT_MODES = ("auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut")
LayoutModeLiteral = Literal["auto", "single_crop", "blurred_pillarbox", "stacked_split", "speaker_cut"]
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1", "localhost", "::1", "[::1]"]


def _ass_color_to_hex(ass_color: str) -> str:
    raw = ass_color.strip().upper()
    if raw.startswith("&H") and len(raw) == 10:
        bb, gg, rr = raw[4:6], raw[6:8], raw[8:10]
        return f"#{rr}{gg}{bb}"
    return "#FFFFFF"


def serialize_preset(p: SubtitleStylePreset) -> dict[str, Any]:
    return {
        "name": p.name,
        "display_name": p.display_name,
        "description": p.description,
        "font_name": p.font_name,
        "font_size": p.font_size,
        "primary_hex": _ass_color_to_hex(p.primary_color),
        "active_hex": _ass_color_to_hex(p.secondary_color),
        "outline_hex": _ass_color_to_hex(p.outline_color),
        "back_hex": _ass_color_to_hex(p.back_color),
        "bold": p.bold,
        "italic": p.italic,
        "border_style": p.border_style,
        "outline": p.outline,
        "shadow": p.shadow,
        "uppercase": p.uppercase,
        "active_word_mode": p.active_word_mode,
        "pop_scale_percent": p.pop_scale_percent,
        "glow_blur": p.glow_blur,
        "recommended_for": list(p.recommended_for),
    }


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _load_project_transcript_words(
    project_dir: Path,
    candidate_id: Optional[str] = None,
    pad_seconds: float = 15.0,
) -> dict[str, Any]:
    """Read word-level timestamps from ``source/transcript.json`` for the Recut Modal."""
    clip_start: Optional[float] = None
    clip_end: Optional[float] = None
    if candidate_id:
        state = load_board_state(project_dir)
        cs = state.get("clip_studio") or {}
        for clip in cs.get("clips") or []:
            if clip.get("candidate_id") == candidate_id:
                clip_start = float(clip.get("start_seconds") or 0.0)
                clip_end = float(clip.get("end_seconds") or 0.0)
                break

    transcript_data: Any = None
    for rel in (
        "source/transcript.json",
        "artifacts/transcript.json",
        "transcript.json",
    ):
        p = project_dir / rel
        if p.is_file():
            try:
                transcript_data = json.loads(p.read_text(encoding="utf-8"))
                break
            except (OSError, json.JSONDecodeError):
                continue

    segments: list[dict[str, Any]] = []
    if isinstance(transcript_data, dict):
        raw_segs = transcript_data.get("segments") or transcript_data.get("transcript") or []
        if isinstance(raw_segs, list):
            segments = [s for s in raw_segs if isinstance(s, dict)]
    elif isinstance(transcript_data, list):
        segments = [s for s in transcript_data if isinstance(s, dict)]

    words: list[dict[str, Any]] = []
    win_lo = max(0.0, clip_start - pad_seconds) if clip_start is not None else 0.0
    win_hi = (clip_end + pad_seconds) if (clip_end is not None and clip_end > 0) else float("inf")

    for seg in segments:
        seg_words = seg.get("words")
        if isinstance(seg_words, list) and seg_words:
            for w in seg_words:
                if not isinstance(w, dict):
                    continue
                ws = float(w.get("start") or 0.0)
                we = float(w.get("end") or ws)
                if we < win_lo or ws > win_hi:
                    continue
                text = str(w.get("word") or w.get("text") or "").strip()
                if text:
                    words.append({"word": text, "start": round(ws, 3), "end": round(we, 3)})
        else:
            ss = float(seg.get("start") or 0.0)
            se = float(seg.get("end") or (ss + float(seg.get("duration") or 0.0)))
            if se < win_lo or ss > win_hi:
                continue
            tokens = str(seg.get("text") or "").split()
            if not tokens:
                continue
            step = max(0.05, (se - ss) / len(tokens)) if se > ss else 0.25
            for idx, tok in enumerate(tokens):
                ws = ss + idx * step
                we = min(se, ws + step) if se > ss else ws + step
                words.append({"word": tok, "start": round(ws, 3), "end": round(we, 3)})

    return {
        "candidate_id": candidate_id,
        "clip_start_seconds": clip_start,
        "clip_end_seconds": clip_end,
        "window_start": round(win_lo, 3),
        "window_end": None if win_hi == float("inf") else round(win_hi, 3),
        "words": words,
    }


def _check_optional_project_id(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    cleaned = val.strip()
    if not cleaned:
        return None
    if not is_valid_project_id(cleaned):
        raise ValueError("project_id must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$")
    return cleaned


def _check_finite_number(val: Any, *, name: str) -> float:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        raise ValueError(f"{name} must be a finite number (not boolean)")
    f = float(val)
    if not math.isfinite(f):
        raise ValueError(f"{name} must be finite")
    return f


# --- Pydantic request bodies -----------------------------------------------

class StartJobRequest(BaseModel):
    source_input: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    clip_count: int = Field(default=2, ge=1, le=10)
    style_preset: str = Field(default="hinglish_impact")
    layout_mode: LayoutModeLiteral = Field(default="auto")
    enable_punch_in: bool = Field(default=True)

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)


class MessageRequest(BaseModel):
    text: str = Field(..., min_length=1)
    client_op_id: Optional[str] = None


class ApproveRequest(BaseModel):
    approved_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    style_preset: Optional[str] = None
    layout_mode: Optional[LayoutModeLiteral] = None
    enable_punch_in: Optional[bool] = None
    notes: str = ""
    project_id: Optional[str] = None

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)


class ReframeRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    crop_overrides: dict[str, Any] = Field(default_factory=dict)
    project_id: Optional[str] = None
    style_preset: Optional[str] = None
    enable_punch_in: Optional[bool] = None

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)


class RecutRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    start_seconds: float
    end_seconds: float
    project_id: Optional[str] = None
    style_preset: Optional[str] = None
    layout_mode: Optional[LayoutModeLiteral] = None

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)

    @field_validator("start_seconds", mode="before")
    @classmethod
    def _val_start(cls, v: Any) -> float:
        f = _check_finite_number(v, name="start_seconds")
        if f < 0.0:
            raise ValueError("start_seconds must be >= 0")
        return f

    @field_validator("end_seconds", mode="before")
    @classmethod
    def _val_end(cls, v: Any) -> float:
        f = _check_finite_number(v, name="end_seconds")
        if f <= 0.0:
            raise ValueError("end_seconds must be > 0")
        return f


class StyleChangeRequest(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    style_preset: str = Field(..., min_length=1)
    project_id: Optional[str] = None
    layout_mode: Optional[LayoutModeLiteral] = None

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)


class ExportRequest(BaseModel):
    clip_ids: list[str] = Field(..., min_length=1)
    project_id: Optional[str] = None

    @field_validator("project_id")
    @classmethod
    def _val_pid(cls, v: Optional[str]) -> Optional[str]:
        return _check_optional_project_id(v)


def _probe_face_backend() -> str:
    with MultiFaceDetector() as det:
        return det.backend


def create_app(
    *,
    store: Optional[SessionStore] = None,
    supervisor: Optional[SupervisorManager] = None,
    studio_token: Optional[str] = None,
    enable_watcher: bool = True,
    allowed_hosts: Optional[list[str]] = None,
) -> FastAPI:
    """Create the Studio FastAPI app with isolated dependencies for clean testing."""
    session_store = store or SessionStore()
    mgr = supervisor or SupervisorManager(session_store)
    token = studio_token or generate_studio_token()
    hosts = list(allowed_hosts) if allowed_hosts is not None else list(DEFAULT_ALLOWED_HOSTS)

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        watch_task = asyncio.create_task(backlot_server._watch_projects()) if enable_watcher else None
        app.state.watch_task = watch_task
        try:
            yield
        finally:
            await mgr.shutdown()
            if watch_task is not None:
                watch_task.cancel()
                with suppress(asyncio.CancelledError):
                    await watch_task

    app = FastAPI(title="AI Video Lab Studio", docs_url=None, redoc_url=None, lifespan=_lifespan)
    app.state.studio_token = token
    app.state.store = session_store
    app.state.supervisor = mgr

    def _render_index_html() -> HTMLResponse:
        index_path = STUDIO_UI_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=503, detail="Studio UI assets not built yet.")
        html = index_path.read_text(encoding="utf-8")
        html = html.replace("__STUDIO_TOKEN__", token)
        for asset in ("studio.css", "studio.js"):
            p = STUDIO_UI_DIR / asset
            if p.is_file():
                ver = str(int(p.stat().st_mtime))
                html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={ver}")
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    # ---- Health & Presets ------------------------------------------------

    @app.get("/api/studio/health")
    async def studio_health(request: Request) -> dict[str, Any]:
        require_loopback(request)
        fcc, nvenc, face_backend = await asyncio.gather(
            asyncio.to_thread(probe_fcc_health),
            asyncio.to_thread(nvenc_available),
            asyncio.to_thread(_probe_face_backend),
        )
        return {
            "ok": True,
            "app": "studio",
            **fcc,
            "nvenc_available": nvenc,
            "face_detector": face_backend,
            "supervisor_bin": discover_supervisor_bin(mgr._supervisor_bin_override),
        }

    @app.get("/api/studio/presets")
    async def studio_presets(request: Request) -> list[dict[str, Any]]:
        require_loopback(request)
        return [serialize_preset(p) for p in SUBTITLE_STYLE_PRESETS.values()]

    # ---- Projects (Read-Only Reuse of Backlot) ---------------------------

    @app.get("/api/studio/projects")
    async def studio_projects(request: Request) -> list[dict[str, Any]]:
        require_loopback(request)
        return await asyncio.to_thread(backlot_server._cached_summaries)

    @app.get("/api/studio/project/{project_id}/state")
    async def studio_project_state(project_id: str, request: Request) -> dict[str, Any]:
        require_loopback(request)
        project_dir = backlot_server._safe_project_dir(project_id)
        state = await asyncio.to_thread(load_board_state, project_dir)
        state["crop_drafts"] = await asyncio.to_thread(session_store.get_crop_drafts, project_id)
        return state

    @app.get("/api/studio/project/{project_id}/transcript")
    async def studio_project_transcript(
        project_id: str,
        request: Request,
        candidate_id: Optional[str] = None,
    ) -> dict[str, Any]:
        require_loopback(request)
        project_dir = backlot_server._safe_project_dir(project_id)
        return await asyncio.to_thread(_load_project_transcript_words, project_dir, candidate_id)

    @app.get("/api/studio/project/{project_id}/events")
    async def studio_project_events(project_id: str, request: Request) -> StreamingResponse:
        require_loopback(request)
        backlot_server._safe_project_dir(project_id)

        async def stream():
            q = backlot_server.hub.subscribe(project_id)
            try:
                yield _sse({"type": "hello", "project_id": project_id})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    yield _sse({"type": "change", "project_id": project_id})
            finally:
                backlot_server.hub.unsubscribe(q)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ---- Supervisor Sessions & Commands ----------------------------------

    @app.get("/api/studio/sessions")
    async def list_sessions(request: Request) -> list[dict[str, Any]]:
        require_loopback(request)
        return await asyncio.to_thread(session_store.list_sessions)

    @app.get("/api/studio/sessions/{session_id}")
    async def get_session(session_id: str, request: Request) -> dict[str, Any]:
        require_loopback(request)
        session = await asyncio.to_thread(session_store.get_session, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown session")
        pid = session.get("project_id")
        msgs = await asyncio.to_thread(session_store.list_messages, session_id)
        drafts = await asyncio.to_thread(session_store.get_crop_drafts, pid) if pid else {}
        return {
            **session,
            "running": mgr.is_running(session_id),
            "messages": msgs,
            "crop_drafts": drafts,
        }

    @app.get("/api/studio/sessions/{session_id}/stream")
    async def session_stream(
        session_id: str,
        request: Request,
        after_id: int = 0,
    ) -> StreamingResponse:
        require_loopback(request)
        session = await asyncio.to_thread(session_store.get_session, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown session")

        async def stream():
            q = mgr.subscribe(session_id)
            sent_msg_ids: set[int] = set()
            try:
                yield _sse({"type": "hello", "session_id": session_id, "status": session["status"]})
                replayed = await asyncio.to_thread(session_store.list_messages, session_id, after_id)
                for msg in replayed:
                    sent_msg_ids.add(int(msg["id"]))
                    yield _sse({"type": "replay", "message": msg})
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield _sse({"type": "heartbeat", "ts": time.time()})
                        continue
                    msg_obj = evt.get("message") if isinstance(evt, dict) else None
                    if isinstance(msg_obj, dict) and msg_obj.get("id") is not None:
                        mid = int(msg_obj["id"])
                        if mid in sent_msg_ids:
                            continue
                        sent_msg_ids.add(mid)
                    yield _sse(evt)
            finally:
                mgr.unsubscribe(session_id, q)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def _map_supervisor_errors(exc: Exception) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, SessionBusyError):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, SupervisorNotFoundError):
            return HTTPException(status_code=503, detail=str(exc))
        if isinstance(exc, ValueError):
            return HTTPException(status_code=400, detail=str(exc))
        return HTTPException(status_code=500, detail=str(exc))

    def _validate_preset(preset_name: Optional[str]) -> None:
        if preset_name is not None and preset_name not in SUBTITLE_STYLE_PRESETS:
            raise HTTPException(status_code=400, detail=f"Unknown style_preset: {preset_name}")

    @app.post("/api/studio/jobs", status_code=201)
    async def create_job(body: StartJobRequest, request: Request) -> dict[str, Any]:
        require_studio_write(request, token)
        _validate_preset(body.style_preset)
        try:
            return await mgr.start_url_job(
                source_input=body.source_input,
                project_id=body.project_id,
                clip_count=body.clip_count,
                style_preset=body.style_preset,
                layout_mode=body.layout_mode,
                enable_punch_in=body.enable_punch_in,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/message", status_code=202)
    async def post_message(
        session_id: str, body: MessageRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        try:
            return await mgr.send_message(
                session_id, body.text, client_op_id=body.client_op_id
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/approve", status_code=202)
    async def post_approve(
        session_id: str, body: ApproveRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        _validate_preset(body.style_preset)
        try:
            return await mgr.send_approval(
                session_id,
                approved_ids=body.approved_ids,
                rejected_ids=body.rejected_ids,
                style_preset=body.style_preset,
                layout_mode=body.layout_mode,
                enable_punch_in=body.enable_punch_in,
                notes=body.notes,
                project_id=body.project_id,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/reframe", status_code=202)
    async def post_reframe(
        session_id: str, body: ReframeRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        _validate_preset(body.style_preset)
        try:
            return await mgr.send_reframe_override(
                session_id,
                candidate_id=body.candidate_id,
                crop_overrides=body.crop_overrides,
                project_id=body.project_id,
                style_preset=body.style_preset,
                enable_punch_in=body.enable_punch_in,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/recut", status_code=202)
    async def post_recut(
        session_id: str, body: RecutRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        _validate_preset(body.style_preset)
        try:
            return await mgr.send_recut(
                session_id,
                candidate_id=body.candidate_id,
                start_seconds=body.start_seconds,
                end_seconds=body.end_seconds,
                project_id=body.project_id,
                style_preset=body.style_preset,
                layout_mode=body.layout_mode,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/style", status_code=202)
    async def post_style(
        session_id: str, body: StyleChangeRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        _validate_preset(body.style_preset)
        try:
            return await mgr.send_style_change(
                session_id,
                candidate_id=body.candidate_id,
                style_preset=body.style_preset,
                project_id=body.project_id,
                layout_mode=body.layout_mode,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/export", status_code=202)
    async def post_export(
        session_id: str, body: ExportRequest, request: Request
    ) -> dict[str, Any]:
        require_studio_write(request, token)
        try:
            return await mgr.send_export(
                session_id,
                clip_ids=body.clip_ids,
                project_id=body.project_id,
            )
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    @app.post("/api/studio/sessions/{session_id}/stop")
    async def post_stop(session_id: str, request: Request) -> dict[str, Any]:
        require_studio_write(request, token)
        try:
            return await mgr.stop_run(session_id)
        except Exception as exc:
            raise _map_supervisor_errors(exc)

    # ---- Media & Thumbnails (Path-Jailed Reuse of Backlot) ---------------

    @app.get("/thumb/{project_id}/{file_path:path}")
    async def thumb(project_id: str, file_path: str, request: Request, w: int = 640) -> FileResponse:
        require_loopback(request)
        project_dir = backlot_server._safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        width = min(backlot_server.THUMB_WIDTHS, key=lambda x: abs(x - w))
        cached = await asyncio.to_thread(backlot_server._thumbnail_for, target, width)
        if cached is None:
            if target.suffix.lower() in {".mp4", ".webm", ".mov"}:
                raise HTTPException(status_code=404, detail="no poster frame available")
            return FileResponse(target)
        return FileResponse(cached, media_type="image/jpeg")

    @app.get("/media/{project_id}/{file_path:path}")
    async def media(project_id: str, file_path: str, request: Request) -> FileResponse:
        require_loopback(request)
        project_dir = backlot_server._safe_project_dir(project_id)
        target = (project_dir / file_path).resolve()
        try:
            target.relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="path escapes project")
        if not target.is_file():
            raise HTTPException(status_code=404, detail="media not found")
        return FileResponse(target)

    # ---- Studio UI -------------------------------------------------------

    @app.get("/")
    async def studio_index(request: Request) -> HTMLResponse:
        require_loopback(request)
        return _render_index_html()

    if STUDIO_UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=STUDIO_UI_DIR), name="studio_ui")
    if BACKLOT_UI_DIR.is_dir():
        app.mount("/backlot-ui", StaticFiles(directory=BACKLOT_UI_DIR), name="backlot_ui")

    @app.middleware("http")
    async def ui_no_cache(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/ui") or path.startswith("/backlot-ui"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=hosts,
        www_redirect=False,
    )
    return app


app = create_app()
