"""Top-Supervisor process manager driving ``fcc-claude`` via stream-json NDJSON & ``--resume``.

Architecture (`MASTER_04` Section 4.3):
- Spawns ``fcc-claude -p <directive> --output-format stream-json --verbose``
  with ``cwd = REPO_ROOT`` and ``CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1``.
- Captures ``claude_session_id`` on Turn 1 and passes ``--resume <id>`` on all
  subsequent turns (chat, 1-click Approve, Reframe Override, Recut, Export).
- Enforces strict 1-active-turn-per-session concurrency via ``asyncio.Lock``
  (raises ``SessionBusyError`` -> HTTP 409 Conflict on overlap).
- Parses NDJSON stream into typed Studio SSE events (``session.init``,
  ``message.text``, ``tool.start``, ``tool.finish``, ``session.linked_project``,
  ``run.done``) and persists messages in ``SessionStore`` (``.studio/sessions.sqlite``).
- Auto-links ``session.project_id`` whenever a tool_use argument references
  ``projects/<id>/`` so the Right Pane Clip Studio switches automatically!
- Clean Windows process-tree cancellation via ``taskkill /F /T /PID`` fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from backlot.state import PROJECTS_DIR, load_board_state
from lib.events import infer_project_dir
from lib.paths import REPO_ROOT
from studio import prompts
from studio.session_store import SessionStore

logger = logging.getLogger(__name__)

_PROJECT_PATH_RE = re.compile(r"projects[\\/]([A-Za-z0-9][A-Za-z0-9._-]{0,80})")


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

    for name in ("fcc-claude", "fcc-claude.exe", "fcc-claude.cmd", "claude"):
        found = shutil.which(name)
        if found:
            return found

    local_bin = Path.home() / ".local" / "bin"
    for name in ("fcc-claude.exe", "fcc-claude.cmd", "fcc-claude"):
        p = local_bin / name
        if p.is_file():
            return str(p)
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


def _extract_project_id_from_inputs(tool_input: Any) -> Optional[str]:
    """Infer ``project_id`` from a tool_use input dict or text."""
    if isinstance(tool_input, dict):
        pid = tool_input.get("project_id")
        if isinstance(pid, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", pid):
            return pid
        inferred = infer_project_dir(tool_input)
        if inferred is not None:
            return inferred.name
        blob = json.dumps(tool_input, default=str)
    else:
        blob = str(tool_input or "")
    m = _PROJECT_PATH_RE.search(blob)
    return m.group(1) if m else None


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

        self._active_procs: dict[str, asyncio.subprocess.Process] = {}
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._stopped_sessions: set[str] = set()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._seen_op_ids: dict[str, set[str]] = {}

    def _resolve_command(self, directive: str, claude_session_id: str | None) -> list[str]:
        if self._supervisor_args_prefix:
            cmd = list(self._supervisor_args_prefix)
        else:
            binary = discover_supervisor_bin(self._supervisor_bin_override)
            if not binary:
                raise SupervisorNotFoundError(
                    "Top Supervisor CLI ('fcc-claude') not found on PATH. "
                    "Install Free Claude Code or set STUDIO_SUPERVISOR_BIN."
                )
            cmd = [binary]
        if claude_session_id:
            cmd.extend(["--resume", claude_session_id])
        cmd.extend(["-p", directive, "--output-format", "stream-json", "--verbose"])
        return cmd

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
        """Return True if this ``client_op_id`` was already processed (duplicate click)."""
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

        title = project_id or Path(cleaned.rstrip("/\\")).name or cleaned[:48]
        session = self.store.create_session(
            title=title[:80],
            source_input=cleaned,
            project_id=project_id,
            status="running",
        )
        sid = session["session_id"]
        directive = prompts.build_start_job_prompt(
            source_input=cleaned,
            project_id=project_id,
            clip_count=clip_count,
            style_preset=style_preset,
            layout_mode=layout_mode,
            enable_punch_in=enable_punch_in,
        )
        display_summary = (
            f"Start production: {cleaned} "
            f"(clips≤{clip_count}, preset={style_preset}, layout={layout_mode}, punch_in={enable_punch_in})"
        )
        await self._launch_turn(sid, directive, user_display=display_summary)
        return self.store.get_session(sid) or session

    async def send_message(
        self,
        session_id: str,
        text: str,
        *,
        client_op_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        if self._check_and_mark_op(session_id, client_op_id):
            return session
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Message text cannot be empty.")
        await self._launch_turn(session_id, cleaned, user_display=cleaned)
        return self.store.get_session(session_id) or session

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
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid:
            raise ValueError("No project linked to this session yet.")
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
        return self.store.get_session(session_id) or session

    async def send_reframe_override(
        self,
        session_id: str,
        *,
        candidate_id: str,
        crop_overrides: dict[str, Any],
        project_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid:
            raise ValueError("No project linked to this session yet.")
        self.store.save_crop_draft(pid, candidate_id, crop_overrides)
        directive = prompts.build_reframe_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            crop_overrides=crop_overrides,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Apply Reframe overrides on {candidate_id} ({len(crop_overrides)} scene(s))",
        )
        return self.store.get_session(session_id) or session

    async def send_recut(
        self,
        session_id: str,
        *,
        candidate_id: str,
        start_seconds: float,
        end_seconds: float,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid:
            raise ValueError("No project linked to this session yet.")
        if end_seconds <= start_seconds or start_seconds < 0:
            raise ValueError("Invalid recut window: end_seconds must exceed start_seconds >= 0.")
        directive = prompts.build_recut_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Recut {candidate_id} to {start_seconds:.2f}s–{end_seconds:.2f}s",
        )
        return self.store.get_session(session_id) or session

    async def send_style_change(
        self,
        session_id: str,
        *,
        candidate_id: str,
        style_preset: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid:
            raise ValueError("No project linked to this session yet.")
        directive = prompts.build_style_change_prompt(
            project_id=pid,
            candidate_id=candidate_id,
            style_preset=style_preset,
        )
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Change subtitle preset on {candidate_id} -> {style_preset}",
        )
        return self.store.get_session(session_id) or session

    async def send_export(
        self,
        session_id: str,
        *,
        clip_ids: list[str],
        project_id: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        pid = project_id or session.get("project_id")
        if not pid:
            raise ValueError("No project linked to this session yet.")
        directive = prompts.build_export_prompt(project_id=pid, clip_ids=clip_ids)
        await self._launch_turn(
            session_id,
            directive,
            user_display=f"Export approved clips: {', '.join(clip_ids)}",
        )
        return self.store.get_session(session_id) or session

    async def stop_run(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_session(session_id)
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
        updated = self.store.update_session(session_id, status="stopped")
        msg = self.store.append_message(
            session_id, "system", {"text": "Supervisor run stopped by user."}
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
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
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

    async def _launch_turn(self, session_id: str, directive: str, *, user_display: str) -> None:
        if self.is_running(session_id):
            raise SessionBusyError(f"Session {session_id} already has an active Supervisor turn.")

        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")

        # Validate executable availability up front before transitioning state
        cmd = self._resolve_command(directive, session.get("claude_session_id"))

        self._stopped_sessions.discard(session_id)
        user_msg = self.store.append_message(
            session_id, "user", {"text": user_display, "directive": directive}
        )
        self.store.update_session(session_id, status="running", last_error=None)
        self._publish(session_id, {"type": "message.user", "message": user_msg})
        self._publish(session_id, {"type": "run.start", "session_id": session_id})

        task = asyncio.create_task(self._run_turn(session_id, cmd))
        self._active_tasks[session_id] = task

    async def _run_turn(self, session_id: str, cmd: list[str]) -> None:
        child_env = os.environ.copy()
        child_env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        child_env.setdefault("PYTHONIOENCODING", "utf-8")

        proc: Optional[asyncio.subprocess.Process] = None
        stderr_chunks: list[str] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
            )
            self._active_procs[session_id] = proc

            async def _drain_stderr() -> None:
                assert proc is not None and proc.stderr is not None
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    stderr_chunks.append(line.decode("utf-8", errors="replace").rstrip())

            stderr_task = asyncio.create_task(_drain_stderr())

            assert proc.stdout is not None
            while True:
                raw_line = await proc.stdout.readline()
                if not raw_line:
                    break
                line_str = raw_line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue
                self._handle_stream_line(session_id, line_str)

            await proc.wait()
            await stderr_task

            if session_id in self._stopped_sessions:
                return

            if proc.returncode == 0:
                next_status = self._infer_post_turn_status(session_id)
                self.store.update_session(session_id, status=next_status, last_error=None)
                self._publish(
                    session_id,
                    {"type": "run.done", "status": next_status, "exit_code": 0},
                )
            else:
                err_tail = "\n".join(stderr_chunks[-10:]) or f"Supervisor exited with code {proc.returncode}"
                self.store.update_session(session_id, status="error", last_error=err_tail[:500])
                err_msg = self.store.append_message(
                    session_id, "system", {"text": err_tail[:500], "is_error": True}
                )
                self._publish(
                    session_id,
                    {"type": "run.done", "status": "error", "error": err_tail[:500], "message": err_msg},
                )
        except asyncio.CancelledError:
            if proc is not None and proc.returncode is None:
                await self._terminate_process_tree(proc)
            raise
        except Exception as exc:
            logger.exception("Supervisor turn crashed for %s", session_id)
            err = str(exc)
            self.store.update_session(session_id, status="error", last_error=err[:500])
            err_msg = self.store.append_message(
                session_id, "system", {"text": err[:500], "is_error": True}
            )
            self._publish(
                session_id,
                {"type": "run.done", "status": "error", "error": err[:500], "message": err_msg},
            )
        finally:
            self._active_procs.pop(session_id, None)
            self._active_tasks.pop(session_id, None)

    def _infer_post_turn_status(self, session_id: str) -> str:
        session = self.store.get_session(session_id) or {}
        pid = session.get("project_id")
        if pid:
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

    def _maybe_link_project(self, session_id: str, project_id: str | None) -> None:
        if not project_id:
            return
        session = self.store.get_session(session_id)
        if session and session.get("project_id") != project_id:
            self.store.update_session(session_id, project_id=project_id)
            self._publish(
                session_id,
                {"type": "session.linked_project", "project_id": project_id},
            )

    def _handle_stream_line(self, session_id: str, line_str: str) -> None:
        try:
            evt = json.loads(line_str)
        except json.JSONDecodeError:
            # Non-JSON line (e.g. plain diagnostic text) -> surface cleanly as assistant text
            msg = self.store.append_message(session_id, "assistant", {"text": line_str})
            self._publish(session_id, {"type": "message.text", "message": msg})
            return

        if not isinstance(evt, dict):
            return

        # Persist claude_session_id whenever reported (system init or result)
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
                    self._maybe_link_project(session_id, _extract_project_id_from_inputs(tool_input))
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
