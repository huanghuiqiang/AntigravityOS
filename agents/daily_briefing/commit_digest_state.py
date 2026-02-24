from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class DigestRunState:
    digest_key: str
    date: str
    timezone: str
    repos: str
    authors: str
    status: str
    trace_id: str
    commit_count: int
    chunk_count: int
    error_message: str | None


class CommitDigestStateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS digest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                digest_key TEXT NOT NULL,
                date TEXT NOT NULL,
                timezone TEXT NOT NULL,
                repos TEXT NOT NULL,
                authors TEXT NOT NULL,
                status TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                commit_count INTEGER NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                force_send INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_digest_key ON digest_runs(digest_key)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_digest_status ON digest_runs(status)"
        )
        columns = {
            str(row[1])
            for row in self._conn.execute("PRAGMA table_info(digest_runs)").fetchall()
        }
        if "chunk_count" not in columns:
            self._conn.execute("ALTER TABLE digest_runs ADD COLUMN chunk_count INTEGER NOT NULL DEFAULT 0")
        self._conn.commit()

    def begin(self) -> None:
        self._conn.execute("BEGIN")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def is_success(self, digest_key: str) -> bool:
        row = self._conn.execute(
            "SELECT id FROM digest_runs WHERE digest_key = ? AND status = 'success' LIMIT 1",
            (digest_key,),
        ).fetchone()
        return row is not None

    def record(self, state: DigestRunState, *, force_send: bool) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO digest_runs (
                digest_key, date, timezone, repos, authors,
                status, trace_id, commit_count, chunk_count, force_send,
                created_at, updated_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.digest_key,
                state.date,
                state.timezone,
                state.repos,
                state.authors,
                state.status,
                state.trace_id,
                state.commit_count,
                state.chunk_count,
                1 if force_send else 0,
                now,
                now,
                state.error_message,
            ),
        )

    def recent_failures(self, *, limit: int = 2) -> int:
        rows = self._conn.execute(
            "SELECT status FROM digest_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        statuses = [str(row[0]) for row in rows]
        if len(statuses) < limit:
            return 0
        return limit if all(status == "failed" for status in statuses) else 0
