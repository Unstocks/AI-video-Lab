"""SQLite session, transcript, and crop-draft store for Studio (.studio/sessions.sqlite).

Lives strictly outside ``projects/`` so Backlot's watchfiles observer is never
spammed by Studio UI session writes. Uses WAL mode + explicit connection closing
so Windows file handles never leak.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from lib.paths import REPO_ROOT

DEFAULT_DB_PATH = REPO_ROOT / ".studio" / "sessions.sqlite"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id         TEXT PRIMARY KEY,
    claude_session_id  TEXT,
    project_id         TEXT,
    title              TEXT NOT NULL,
    source_input       TEXT,
    status             TEXT NOT NULL,
    last_error         TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role               TEXT NOT NULL,
    content_json       TEXT NOT NULL,
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS crop_drafts (
    project_id         TEXT NOT NULL,
    candidate_id       TEXT NOT NULL,
    overrides_json     TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (project_id, candidate_id)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    """Thread-safe SQLite repository with WAL mode and leak-free connection lifecycle."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 15000")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(_SCHEMA_SQL)

    def create_session(
        self,
        *,
        title: str,
        source_input: Optional[str] = None,
        project_id: Optional[str] = None,
        status: str = "idle",
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        sid = session_id or f"ses_{uuid.uuid4().hex[:10]}"
        now = _utc_now()
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, claude_session_id, project_id, title,
                    source_input, status, last_error, created_at, updated_at
                ) VALUES (?, NULL, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (sid, project_id, title, source_input, status, now, now),
            )
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (sid,)
            ).fetchone()
            return dict(row)

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (int(limit),)
            ).fetchall()
            return [dict(r) for r in rows]

    def update_session(
        self,
        session_id: str,
        *,
        claude_session_id: Any = ...,
        project_id: Any = ...,
        title: Any = ...,
        status: Any = ...,
        last_error: Any = ...,
    ) -> Optional[dict[str, Any]]:
        updates: list[str] = ["updated_at = ?"]
        params: list[Any] = [_utc_now()]
        for col, val in (
            ("claude_session_id", claude_session_id),
            ("project_id", project_id),
            ("title", title),
            ("status", status),
            ("last_error", last_error),
        ):
            if val is not ...:
                updates.append(f"{col} = ?")
                params.append(val)
        params.append(session_id)
        with self._lock, self._connection() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(updates)} WHERE session_id = ?",
                params,
            )
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def append_message(
        self, session_id: str, role: str, content: dict[str, Any]
    ) -> dict[str, Any]:
        now = _utc_now()
        payload_str = json.dumps(content, ensure_ascii=False, default=str)
        with self._lock, self._connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (session_id, role, content_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, payload_str, now),
            )
            msg_id = int(cur.lastrowid or 0)
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
        return {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
        }

    def list_messages(self, session_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content_json, created_at
                FROM messages
                WHERE session_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (session_id, int(after_id)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            try:
                content = json.loads(r["content_json"])
            except json.JSONDecodeError:
                content = {"text": r["content_json"]}
            out.append({
                "id": int(r["id"]),
                "session_id": r["session_id"],
                "role": r["role"],
                "content": content,
                "created_at": r["created_at"],
            })
        return out

    def save_crop_draft(
        self, project_id: str, candidate_id: str, overrides: dict[str, Any]
    ) -> dict[str, Any]:
        now = _utc_now()
        raw = json.dumps(overrides, ensure_ascii=False)
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO crop_drafts (project_id, candidate_id, overrides_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, candidate_id)
                DO UPDATE SET overrides_json = excluded.overrides_json, updated_at = excluded.updated_at
                """,
                (project_id, candidate_id, raw, now),
            )
        return {
            "project_id": project_id,
            "candidate_id": candidate_id,
            "overrides": overrides,
            "updated_at": now,
        }

    def get_crop_drafts(self, project_id: str) -> dict[str, dict[str, Any]]:
        with self._lock, self._connection() as conn:
            rows = conn.execute(
                "SELECT candidate_id, overrides_json FROM crop_drafts WHERE project_id = ?",
                (project_id,),
            ).fetchall()
        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            try:
                result[r["candidate_id"]] = json.loads(r["overrides_json"])
            except json.JSONDecodeError:
                continue
        return result
