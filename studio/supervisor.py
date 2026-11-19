"""Top-Supervisor process manager driving ``fcc-claude`` via stream-json NDJSON & ``--resume``.

Hardened invariants:
- Per-session ``asyncio.Lock`` serializes start/stop/send cleanly (zero stop/start
  races, zero ghost sessions, HTTP 409 on concurrent sends).
- Safe chunked NDJSON line reader (``limit=16 MiB`` + manual chunked scan) so
  large ``tool_result`` transcripts (>64 KiB) NEVER crash ``StreamReader``.
- Bounded stderr ring buffer (``deque(maxlen=200)``).
- Guaranteed subprocess-tree & task cleanup in ``finally:`` on ANY exception
  (async ``taskkill /F /T`` on Windows — never blocks event loop, zero zombies).
- Auto-links ``session.project_id`` ONLY when currently unset and validated as a
  real project slug (never hijacks an explicitly bound project).
"""

from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from backlot.state import PROJECTS_DIR, load_board_state
from lib.events import infer_project_dir
from lib.paths import REPO_ROOT
from studio import prompts
from studio.security import is_valid_project_id
from studio.session_store import SessionStore

logger = logging.getLogger(__name__)

_PROJECT_PATH_RE = re.compile(r"projects[\\/]([A-Za-z0-9][A-Za-z0-9_-]{0,80})")
_STREAM_READER_LIMIT = 16 * 1024 * 1024  # 16 MiB buffer limit
_MAX_LINE_BYTES = 16 * 1024 * 1024


class SessionBusyError(RuntimeError):
    """Raised when a session already has an active Top-Supervisor turn running."""


class SupervisorNotFoundError(RuntimeError):
    """Raised when no ``fcc-claude`` executable is found on PATH or override env."""


def discover_supervisor_bin(override: str | None = None) -> Optional[str]:
    """Locate ``fcc-claude`` (or configured ``STUDIO_SUPERVISOR_BIN``)."""
    candidate = (override or os.environ.get("STUDIO_SUPERVISOR_BIN") or "").strip()
    if candidate:
        if Path(candidate).is_file():
            return str(Path(candidate).resolve())
        found = shutil.which(candidate)
        if found:
            return found

    local_bin = Path.home() / ".local" / "bin"
    for name in ("fcc-claude.exe", "fcc-claude.cmd", "fcc-claude"):
        p = local_bin / name
        if p.is_file():
            return str(p)

    for name in ("fcc-claude", "fcc-claude.exe", "fcc-claude.cmd", "claude"):
        found = shutil.which(name)
        if found:
            return found
    return None


def probe_fcc_health(base_url: str | None = None, timeout: float = 1.5) -> dict[str, Any]:
    """Non-blocking health probe against Free Claude Code loopback server (127.0.0.1:8082)."""
    root = (base_url or os.environ.get("FCC_BASE_URL") or "http://127.0.0.1:8082").rstrip("/")
    url = f"{root}/v1/models?view=messages"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
                models_raw = payload.get("data") if isinstance(payload, dict) else payload
                models: list[str] = []
                if isinstance(models_raw, list):
                    for m in models_raw:
                        if isinstance(m, dict) and m.get("id"):
                            models.append(str(m["id"]))
                        elif isinstance(m, str):
                            models.append(m)
                active = (
                    (payload.get("active_model") if isinstance(payload, dict) else None)
                    or (models[0] if models else "FCC Online")
                )
                return {
                    "fcc_online": True,
                    "fcc_base_url": root,
                    "fcc_active_model": active,
                    "fcc_models": models,
                }
    except Exception:
        pass
    return {
        "fcc_online": False,
        "fcc_base_url": root,
        "fcc_active_model": None,
        "fcc_models": [],
    }


def switch_fcc_model(model_id: str, base_url: str | None = None, timeout: float = 2.5) -> dict[str, Any]:
    """Attempt to switch active model on Free Claude Code loopback server (127.0.0.1:8082)."""
    cleaned = model_id.strip()
    if not cleaned:
        raise ValueError("model_id must be non-empty")
    root = (base_url or os.environ.get("FCC_BASE_URL") or "http://127.0.0.1:8082").rstrip("/")
    payload = json.dumps({"model": cleaned}).encode("utf-8")
    last_err = "FCC server unreachable"
    for path in ("/v1/models/active", "/api/model", "/model"):
        try:
            req = urllib.request.Request(
                f"{root}{path}",
                data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    health = probe_fcc_health(root, timeout=timeout)
                    return {"ok": True, "model": cleaned, **health}
        except Exception as exc:
            last_err = str(exc)
    return {
        "ok": False,
        "model": cleaned,
        "detail": f"Could not switch model on FCC ({last_err}). Switch via FCC CLI or restart FCC with the selected model.",
        **probe_fcc_health(root, timeout=timeout),
    }


def _extract_project_id_from_inputs(tool_input: Any) -> Optional[str]:
    """Infer a validated ``project_id`` from a tool_use input dict or text."""
    if isinstance(tool_input, dict):
        pid = tool_input.get("project_id")
        if is_valid_project_id(pid):
            return str(pid)
        inferred = infer_project_dir(tool_input)
        if inferred is not None and is_valid_project_id(inferred.name):
            return inferred.name
        blob = json.dumps(tool_input, default=str)
    else:
        blob = str(tool_input or "")
    m = _PROJECT_PATH_RE.search(blob)
    cand = m.group(1) if m else None
    return cand if is_valid_project_id(cand) else None


def _summarize_tool_input(tool_input: Any) -> str:
    if isinstance(tool_input, dict):
        keys = [f"{k}={str(v)[:60]}" for k, v in list(tool_input.items())[:4]]
        return ", ".join(keys)
    return str(tool_input or "")[:200]


def _summarize_tool_result(content: Any) -> str:
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    else:
        text = str(content or "")
    return text.strip()[:400]


async def _iter_lines_safe(
    stream: asyncio.StreamReader,
    *,
    chunk_size: int = 65536,
    max_line_bytes: int = _MAX_LINE_BYTES,
) -> AsyncIterator[str]:
    """Yield decoded lines from ``stream`` without EVER raising ``LimitOverrunError``."""
    buf = bytearray()
    oversized = False
    while True:
        chunk = await stream.read(chunk_size)
        if not chunk:
            if buf:
                yield buf.decode("utf-8", errors="replace").rstrip("\r\n")
            return
        start = 0
        while True:
            nl = chunk.find(b"\n", start)
            if nl == -1:
                rem = chunk[start:]
                if not oversized:
                    if len(buf) + len(rem) <= max_line_bytes:
                        buf.extend(rem)
                    else:
                        oversized = True
                        buf.extend(rem[: max(0, max_line_bytes - len(buf))])
                break
            piece = chunk[start:nl]
            if not oversized and len(buf) + len(piece) <= max_line_bytes:
                buf.extend(piece)
            if buf:
                yield buf.decode("utf-8", errors="replace").rstrip("\r")
            buf.clear()
            oversized = False
            start = nl + 1


class SupervisorManager:
    """Owns loopback ``fcc-claude`` subprocesses, SSE subscribers, and SQLite persistence."""

    def __init__(
        self,
        store: SessionStore,
        *,
        supervisor_bin: str | None = None,
        supervisor_args_prefix: list[str] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.store = store
        self._supervisor_bin_override = supervisor_bin
        self._supervisor_args_prefix = list(supervisor_args_prefix or [])
        self.cwd = Path(cwd) if cwd is not None else REPO_ROOT

        self._locks: dict[str, asyncio.Lock] = {}
        self._active_procs: dict[str, asyncio.subprocess.Process] = {}
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._stopped_sessions: set[str] = set()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._seen_op_ids: dict[str, set[str]] = {}

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        lock = self._locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[session_id] = lock
        return lock

    def _resolve_command(
        self, directive: str, claude_session_id: str | None
    ) -> tuple[list[str], Optional[bytes]]:
        """Return ``(argv, stdin_bytes)``.

        Windows ``.cmd`` / ``.bat`` shims truncate multiline CLI args and fail
        past 8 KiB, so for batch shims we pipe the directive cleanly via stdin.
        """
        if self._supervisor_args_prefix:
            cmd = list(self._supervisor_args_prefix)
            is_batch_shim = False
        else:
            binary = discover_supervisor_bin(self._supervisor_bin_override)
            if not binary:
                raise SupervisorNotFoundError(
                    "Top Supervisor CLI ('fcc-claude') not found on PATH. "
                    "Install Free Claude Code or set STUDIO_SUPERVISOR_BIN."
                )
            cmd = [binary]
            is_batch_shim = Path(binary).suffix.lower() in (".cmd", ".bat")

        if claude_session_id:
            cmd.extend(["--resume", claude_session_id])

        if is_batch_shim:
            cmd.extend(["-p", "--output-format", "stream-json", "--verbose"])
            return cmd, (directive + "\n").encode("utf-8")

        cmd.extend(["-p", directive, "--output-format", "stream-json", "--verbose"])
        return cmd, None

    def is_running(self, session_id: str) -> bool:
        task = self._active_tasks.get(session_id)
        return task is not None and not task.done()

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(session_id, set()).add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(session_id)
        if subs:
            subs.discard(q)
            if not subs:
                self._subscribers.pop(session_id, None)

    def _publish(self, session_id: str, event: dict[str, Any]) -> None:
        for q in list(self._subscribers.get(session_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def _check_and_mark_op(self, session_id: str, client_op_id: str | None) -> bool:
        if not client_op_id:
            return False
        bucket = self._seen_op_ids.setdefault(session_id, set())
        if client_op_id in bucket:
            return True
        if len(bucket) > 200:
            bucket.clear()
        bucket.add(client_op_id)
        return False

    async def start_url_job(
        self,
        *,
        source_input: str,
        project_id: str | None = None,
        clip_count: int = 2,
        style_preset: str = "hinglish_impact",
        layout_mode: str = "auto",
        enable_punch_in: bool = True,
    ) -> dict[str, Any]:
        cleaned = source_input.strip()
        if not cleaned:
            raise ValueError("source_input must be a non-empty URL or file path.")
        if project_id is not None and not is_valid_project_id(project_id):
            raise ValueError("Invalid project_id.")

        directive = prompts.build_start_job_prompt(
            source_input=cleaned,
            project_id=project_id,
            clip_count=clip_count,
            style_preset=style_preset,
            layout_mode=layout_mode,
            enable_punch_in=enable_punch_in,
        )
        # Verify CLI executable BEFORE creating a session row (no ghost 'running' rows!)
        self._resolve_command(directive, None)

        title = project_id or Path(cleaned.rstrip("/\\")).name or cleaned[:48]
        session = await asyncio.to_thread(
            self.store.create_session,
            title=title[:80],
            source_input=cleaned,
            project_id=project_id,
            status="idle",
        )
        sid = session["session_id"]
        display_summary = (
            f"Start production: {cleaned} "
            f"(clips<={clip_count}, preset={style_preset}, layout={layout_mode}, punch_in={enable_punch_in})"
        )
        await self._launch_turn(sid, directive, user_display=display_summary)
        return await asyncio.to_thread(self.store.get_session, sid) or session

    async def send_message(
        self,
        session_id: str,
        text: str,
        *,
        client_op_id: str | None = None,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        if self._check_and_mark_op(session_id, client_op_id):
            return session
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Message text cannot be empty.")
        await self._launch_turn(session_id, cleaned, user_display=cleaned)
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_approval(
        self,
        session_id: str,
        *,
        approved_ids: list[str],
        rejected_ids: list[str] | None = None,
        style_preset: str | None = None,
        layout_mode: str | None = None,
        enable_punch_in: bool | None = None,
        notes: str = "",
        project_id: str | None = None,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("No valid project linked to this session yet.")
        directive = prompts.build_approval_prompt(
            project_id=pid,
            approved_ids=approved_ids,
            rejected_ids=rejected_ids or [],
            style_preset=style_preset,
            layout_mode=layout_mode,
            enable_punch_in=enable_punch_in,
            notes=notes,
        )
        label = f"Approved {', '.join(approved_ids) or 'none'} for rendering on RTX 3050"
        await self._launch_turn(session_id, directive, user_display=label)
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_reframe_override(
        self,
        session_id: str,
        *,
        candidate_id: str,
        crop_overrides: dict[str, Any],
        project_id: str | None = None,
        style_preset: str | None = None,
        enable_punch_in: bool | None = None,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("No valid project linked to this session yet.")
        directive = prompts.build_reframe_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            crop_overrides=crop_overrides,
            style_preset=style_preset,
            enable_punch_in=enable_punch_in,
        )
        # Launch turn FIRST (acquires lock & verifies not busy) before persisting draft
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Apply Reframe overrides on {candidate_id} ({len(crop_overrides)} scene(s))",
            pre_commit=lambda: self.store.save_crop_draft(pid, candidate_id, crop_overrides),
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_recut(
        self,
        session_id: str,
        *,
        candidate_id: str,
        start_seconds: float,
        end_seconds: float,
        project_id: str | None = None,
        style_preset: str | None = None,
        layout_mode: str | None = None,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("No valid project linked to this session yet.")
        if end_seconds <= start_seconds or start_seconds < 0:
            raise ValueError("Invalid recut window: end_seconds must exceed start_seconds >= 0.")
        directive = prompts.build_recut_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            style_preset=style_preset,
            layout_mode=layout_mode,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Recut {candidate_id} to {start_seconds:.2f}s–{end_seconds:.2f}s",
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_style_change(
        self,
        session_id: str,
        *,
        candidate_id: str,
        style_preset: str,
        project_id: str | None = None,
        layout_mode: str | None = None,
        corrections: dict[str, str] | None = None,
        margin_v: int | None = None,
        highlight_style: str | None = None,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("No valid project linked to this session yet.")
        directive = prompts.build_style_change_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            style_preset=style_preset,
            layout_mode=layout_mode,
            corrections=corrections,
            margin_v=margin_v,
            highlight_style=highlight_style,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Change subtitle preset on {candidate_id} -> {style_preset}",
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_export(
        self,
        session_id: str,
        *,
        clip_ids: list[str],
        project_id: str | None = None,
        target_resolution: str = "1440p",
        codec: str = "auto",
        clarity_percent: int = 45,
    ) -> dict[str, Any]:
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("No valid project linked to this session yet.")
        directive = prompts.build_export_prompt(
            project_id=pid,
            clip_ids=clip_ids,
            target_resolution=target_resolution,
            codec=codec,
            clarity_percent=clarity_percent,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Export approved clips in {target_resolution.upper()}: {', '.join(clip_ids)}",
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def start_production(
        self,
        *,
        pipeline_type: str,
        brief_prompt: str = "",
        project_id: str | None = None,
        source_input: str | None = None,
        reference_url: str | None = None,
        style_playbook: str | None = None,
        media_profile: str | None = None,
        render_runtime: str | None = None,
        composition_mode: str | None = None,
        style_preset: str | None = None,
        budget_usd: float | None = None,
        clip_count: int = 2,
        layout_mode: str = "auto",
        enable_punch_in: bool = True,
    ) -> dict[str, Any]:
        """Launch ANY OpenMontage pipeline through the Top Supervisor."""
        if project_id is not None and not is_valid_project_id(project_id):
            raise ValueError("Invalid project_id.")
        cleaned_brief = brief_prompt.strip()
        cleaned_source = (source_input or "").strip()
        cleaned_ref = (reference_url or "").strip()
        if not cleaned_brief and not cleaned_source and not cleaned_ref:
            raise ValueError("Provide a brief_prompt, source_input, or reference_url.")

        directive = prompts.build_production_prompt(
            pipeline_type=pipeline_type,
            brief_prompt=cleaned_brief or f"Run {pipeline_type} production",
            project_id=project_id,
            source_input=cleaned_source or None,
            reference_url=cleaned_ref or None,
            style_playbook=style_playbook,
            media_profile=media_profile,
            render_runtime=render_runtime,
            composition_mode=composition_mode,
            style_preset=style_preset,
            budget_usd=budget_usd,
            clip_count=clip_count,
            layout_mode=layout_mode,
            enable_punch_in=enable_punch_in,
        )
        self._resolve_command(directive, None)

        title = (
            project_id
            or (cleaned_brief[:64] if cleaned_brief else "")
            or (Path(cleaned_source.rstrip("/\\")).name if cleaned_source else "")
            or f"{pipeline_type} production"
        )
        session = await asyncio.to_thread(
            self.store.create_session,
            title=title[:80],
            source_input=cleaned_source or cleaned_ref or pipeline_type,
            project_id=project_id,
            status="idle",
        )
        sid = session["session_id"]
        summary_parts = [f"Launch `{pipeline_type}`"]
        if cleaned_brief:
            summary_parts.append(f'"{cleaned_brief[:120]}"')
        if cleaned_source:
            summary_parts.append(f"source={cleaned_source}")
        if style_playbook:
            summary_parts.append(f"playbook={style_playbook}")
        if media_profile:
            summary_parts.append(f"profile={media_profile}")
        await self._launch_turn(sid, directive, user_display=" · ".join(summary_parts))
        return await asyncio.to_thread(self.store.get_session, sid) or session

    async def create_session(
        self,
        *,
        title: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Create an idle Supervisor session (optionally attached to an existing project)."""
        if project_id is not None and not is_valid_project_id(project_id):
            raise ValueError("Invalid project_id.")
        display = (title or "").strip() or (f"Project {project_id}" if project_id else "Executive Producer Chat")
        return await asyncio.to_thread(
            self.store.create_session,
            title=display[:80],
            source_input=None,
            project_id=project_id,
            status="idle",
        )

    async def send_gate_decision(
        self,
        session_id: str,
        *,
        stage: str,
        decision: str,
        notes: str = "",
        project_id: str | None = None,
        render_runtime: str | None = None,
        composition_mode: str | None = None,
    ) -> dict[str, Any]:
        """Approve, revise, or reject ANY human-gated pipeline stage."""
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("Cannot decide stage gate without a valid project_id.")
        if decision.strip().lower() not in ("approve", "revise", "reject"):
            raise ValueError("decision must be 'approve', 'revise', or 'reject'")
        directive = prompts.build_gate_decision_prompt(
            project_id=pid,
            stage=stage.strip(),
            decision=decision.strip().lower(),
            notes=notes,
            render_runtime=render_runtime,
            composition_mode=composition_mode,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Gate [{stage}]: {decision.upper()}" + (f" — {notes.strip()[:120]}" if notes.strip() else ""),
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def send_tool_action(
        self,
        session_id: str,
        *,
        action: str,
        params: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a structured Creator Editor tool action directive to Top Supervisor."""
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid or not is_valid_project_id(pid):
            raise ValueError("Cannot execute tool action without a valid project_id.")
        directive = prompts.build_tool_action_prompt(
            project_id=pid,
            action=action.strip(),
            params=params,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Tool Action [{action.strip()}] on {pid}",
        )
        return await asyncio.to_thread(self.store.get_session, session_id) or session

    async def delete_session(self, session_id: str) -> bool:
        """Stop any running turn and delete the session row + messages."""
        session = await asyncio.to_thread(self.store.get_session, session_id)
        if session is None:
            return False
        if self.is_running(session_id):
            await self.stop_run(session_id)
        return await asyncio.to_thread(self.store.delete_session, session_id)

    async def stop_run(self, session_id: str) -> dict[str, Any]:
        async with self._lock_for(session_id):
            session = await asyncio.to_thread(self.store.get_session, session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")
            self._stopped_sessions.add(session_id)
            proc = self._active_procs.get(session_id)
            if proc is not None and proc.returncode is None:
                await self._terminate_process_tree(proc)
            task = self._active_tasks.get(session_id)
            if task is not None and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            updated = await asyncio.to_thread(
                self.store.update_session, session_id, status="stopped"
            )
            msg = await asyncio.to_thread(
                self.store.append_message,
                session_id,
                "system",
                {"text": "Supervisor run stopped by user."},
            )
            self._publish(session_id, {"type": "run.done", "status": "stopped", "message": msg})
            return updated or session

    async def shutdown(self) -> None:
        """Terminate all running Supervisor subprocesses on server shutdown."""
        for sid in list(self._active_procs.keys()):
            try:
                await self.stop_run(sid)
            except Exception:
                pass

    async def _terminate_process_tree(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        if sys.platform == "win32":
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/F", "/T", "/PID", str(proc.pid),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(killer.wait(), timeout=5.0)
            except Exception:
                pass
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except Exception:
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except Exception:
                pass

    async def _launch_turn(
        self,
        session_id: str,
        directive: str,
        *,
        user_display: str,
        pre_commit: Any = None,
    ) -> None:
        async with self._lock_for(session_id):
            if self.is_running(session_id):
                raise SessionBusyError(f"Session {session_id} already has an active Supervisor turn.")

            session = await asyncio.to_thread(self.store.get_session, session_id)
            if session is None:
                raise KeyError(f"Unknown session: {session_id}")

            cmd, stdin_bytes = self._resolve_command(directive, session.get("claude_session_id"))

            if pre_commit is not None:
                await asyncio.to_thread(pre_commit)

            self._stopped_sessions.discard(session_id)
            user_msg = await asyncio.to_thread(
                self.store.append_message,
                session_id,
                "user",
                {"text": user_display, "directive": directive},
            )
            await asyncio.to_thread(
                self.store.update_session, session_id, status="running", last_error=None
            )
            self._publish(session_id, {"type": "message.user", "message": user_msg})
            self._publish(session_id, {"type": "run.start", "session_id": session_id})

            task = asyncio.create_task(self._run_turn(session_id, cmd, stdin_bytes))
            self._active_tasks[session_id] = task

    async def _run_turn(
        self, session_id: str, cmd: list[str], stdin_bytes: Optional[bytes] = None
    ) -> None:
        child_env = os.environ.copy()
        child_env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        child_env.setdefault("PYTHONIOENCODING", "utf-8")

        proc: Optional[asyncio.subprocess.Process] = None
        stderr_task: Optional[asyncio.Task[Any]] = None
        stderr_chunks: deque[str] = deque(maxlen=200)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.cwd),
                stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=_STREAM_READER_LIMIT,
                env=child_env,
            )
            self._active_procs[session_id] = proc

            if stdin_bytes is not None and proc.stdin is not None:
                proc.stdin.write(stdin_bytes)
                await proc.stdin.drain()
                proc.stdin.close()

            async def _drain_stderr() -> None:
                assert proc is not None and proc.stderr is not None
                async for line_str in _iter_lines_safe(proc.stderr, max_line_bytes=256 * 1024):
                    if line_str:
                        stderr_chunks.append(line_str)

            stderr_task = asyncio.create_task(_drain_stderr())

            assert proc.stdout is not None
            async for line_str in _iter_lines_safe(proc.stdout):
                cleaned = line_str.strip()
                if not cleaned:
                    continue
                await asyncio.to_thread(self._handle_stream_line, session_id, cleaned)

            await proc.wait()
            await stderr_task

            if session_id in self._stopped_sessions:
                return

            if proc.returncode == 0:
                next_status = await asyncio.to_thread(self._infer_post_turn_status, session_id)
                await asyncio.to_thread(
                    self.store.update_session, session_id, status=next_status, last_error=None
                )
                self._publish(
                    session_id,
                    {"type": "run.done", "status": next_status, "exit_code": 0},
                )
            else:
                err_tail = "\n".join(list(stderr_chunks)[-10:]) or f"Supervisor exited with code {proc.returncode}"
                await asyncio.to_thread(
                    self.store.update_session, session_id, status="error", last_error=err_tail[:500]
                )
                err_msg = await asyncio.to_thread(
                    self.store.append_message,
                    session_id,
                    "system",
                    {"text": err_tail[:500], "is_error": True},
                )
                self._publish(
                    session_id,
                    {"type": "run.done", "status": "error", "error": err_tail[:500], "message": err_msg},
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Supervisor turn crashed for %s", session_id)
            err = str(exc)
            await asyncio.to_thread(
                self.store.update_session, session_id, status="error", last_error=err[:500]
            )
            err_msg = await asyncio.to_thread(
                self.store.append_message,
                session_id,
                "system",
                {"text": err[:500], "is_error": True},
            )
            self._publish(
                session_id,
                {"type": "run.done", "status": "error", "error": err[:500], "message": err_msg},
            )
        finally:
            if proc is not None and proc.returncode is None:
                await self._terminate_process_tree(proc)
            if stderr_task is not None and not stderr_task.done():
                stderr_task.cancel()
                try:
                    await asyncio.wait_for(stderr_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            self._active_procs.pop(session_id, None)
            self._active_tasks.pop(session_id, None)

    def _infer_post_turn_status(self, session_id: str) -> str:
        session = self.store.get_session(session_id) or {}
        pid = session.get("project_id")
        if pid and is_valid_project_id(pid):
            proj_dir = PROJECTS_DIR / pid
            if proj_dir.is_dir():
                try:
                    board = load_board_state(proj_dir)
                    stages = board.get("stages") or []
                    if any(s.get("status") == "awaiting_human" for s in stages):
                        return "awaiting_human"
                    pub = next((s for s in stages if s.get("name") == "publish"), None)
                    if pub and pub.get("status") == "completed":
                        return "completed"
                except Exception:
                    pass
        return "idle"

    def _maybe_link_project(
        self, session_id: str, project_id: str | None, *, from_intake_tool: bool = False
    ) -> None:
        """Auto-bind ``session.project_id`` ONLY when currently unset (never hijack existing binding)."""
        if not project_id or not is_valid_project_id(project_id):
            return
        session = self.store.get_session(session_id)
        if not session or session.get("project_id"):
            return
        if not from_intake_tool and not (PROJECTS_DIR / project_id).is_dir():
            return
        self.store.update_session(session_id, project_id=project_id)
        self._publish(
            session_id,
            {"type": "session.linked_project", "project_id": project_id},
        )

    def _handle_stream_line(self, session_id: str, line_str: str) -> None:
        try:
            evt = json.loads(line_str)
        except json.JSONDecodeError:
            msg = self.store.append_message(session_id, "assistant", {"text": line_str[:4000]})
            self._publish(session_id, {"type": "message.text", "message": msg})
            return

        if not isinstance(evt, dict):
            return

        csid = evt.get("session_id")
        if isinstance(csid, str) and csid.strip():
            self.store.update_session(session_id, claude_session_id=csid.strip())
            if evt.get("type") == "system":
                self._publish(
                    session_id,
                    {
                        "type": "session.init",
                        "claude_session_id": csid.strip(),
                        "model": evt.get("model"),
                    },
                )

        etype = evt.get("type")
        if etype == "assistant":
            message_obj = evt.get("message") or {}
            blocks = message_obj.get("content") or []
            if isinstance(blocks, str):
                blocks = [{"type": "text", "text": blocks}]
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        self._maybe_link_project(session_id, _extract_project_id_from_inputs(text))
                        msg = self.store.append_message(session_id, "assistant", {"text": text})
                        self._publish(session_id, {"type": "message.text", "message": msg})
                elif btype == "tool_use":
                    tool_id = str(block.get("id") or "")
                    name = str(block.get("name") or "tool")
                    tool_input = block.get("input") or {}
                    is_intake = name in ("url_intake", "local_media_intake")
                    self._maybe_link_project(
                        session_id,
                        _extract_project_id_from_inputs(tool_input),
                        from_intake_tool=is_intake,
                    )
                    payload = {
                        "tool_id": tool_id,
                        "name": name,
                        "input_summary": _summarize_tool_input(tool_input),
                        "input": tool_input,
                    }
                    msg = self.store.append_message(session_id, "tool_use", payload)
                    self._publish(session_id, {"type": "tool.start", "message": msg, **payload})

        elif etype == "user":
            message_obj = evt.get("message") or {}
            blocks = message_obj.get("content") or []
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_id = str(block.get("tool_use_id") or "")
                    is_err = bool(block.get("is_error", False))
                    summary = _summarize_tool_result(block.get("content"))
                    self._maybe_link_project(session_id, _extract_project_id_from_inputs(summary))
                    payload = {
                        "tool_id": tool_id,
                        "is_error": is_err,
                        "summary": summary,
                    }
                    msg = self.store.append_message(session_id, "tool_result", payload)
                    self._publish(session_id, {"type": "tool.finish", "message": msg, **payload})

        elif etype == "result":
            result_text = str(evt.get("result") or "").strip()
            if result_text:
                self._maybe_link_project(session_id, _extract_project_id_from_inputs(result_text))
            self._publish(
                session_id,
                {
                    "type": "turn.result",
                    "subtype": evt.get("subtype"),
                    "duration_ms": evt.get("duration_ms"),
                    "is_error": bool(evt.get("is_error", False)),
                },
            )
