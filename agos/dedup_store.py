from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agos.config import bouncer_dedup_query_drop_keys, bouncer_dedup_query_drop_prefixes


@dataclass(frozen=True)
class DedupCheckResult:
    exists: bool
    dedup_key: str
    reason: str
    normalized_url: str
    source_host: str


@dataclass(frozen=True)
class DedupMetrics:
    fetched_count: int
    inserted_count: int
    deduped_count: int

    @property
    def dedup_rate(self) -> float:
        if self.fetched_count <= 0:
            return 0.0
        return (self.deduped_count / self.fetched_count) * 100.0


class DedupStore:
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
            CREATE TABLE IF NOT EXISTS dedup_entries (
                dedup_key TEXT PRIMARY KEY,
                source_url TEXT NOT NULL,
                title_norm TEXT NOT NULL,
                source_host TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                note_path TEXT,
                version INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def begin(self) -> None:
        self._conn.execute("BEGIN")

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def normalize_title(self, title: str) -> str:
        return " ".join(title.strip().lower().split())

    def normalize_url(self, url: str) -> tuple[str, str]:
        raw = (url or "").strip()
        if not raw:
            return "", ""

        parts = urlsplit(raw)
        scheme = (parts.scheme or "https").lower()
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]

        path = parts.path or "/"
        if path != "/":
            path = path.rstrip("/")

        drop_keys = bouncer_dedup_query_drop_keys()
        drop_prefixes = bouncer_dedup_query_drop_prefixes()

        query_items: list[tuple[str, str]] = []
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            low = key.lower()
            if low in drop_keys:
                continue
            if any(low.startswith(prefix) for prefix in drop_prefixes):
                continue
            query_items.append((key, value))

        query = urlencode(sorted(query_items), doseq=True)
        normalized = urlunsplit((scheme, host, path, query, ""))
        return normalized, host

    def build_key(self, source_url: str, title: str) -> tuple[str, str, str, str]:
        normalized_url, host = self.normalize_url(source_url)
        title_norm = self.normalize_title(title)
        if normalized_url:
            return f"src:{normalized_url}", "same_source", normalized_url, host
        return f"fallback:{host}|{title_norm}", "same_title_same_source", normalized_url, host

    def check(self, source_url: str, title: str) -> DedupCheckResult:
        dedup_key, reason, normalized_url, host = self.build_key(source_url, title)
        row = self._conn.execute(
            "SELECT dedup_key FROM dedup_entries WHERE dedup_key = ?",
            (dedup_key,),
        ).fetchone()
        return DedupCheckResult(
            exists=row is not None,
            dedup_key=dedup_key,
            reason=reason,
            normalized_url=normalized_url,
            source_host=host,
        )

    def upsert_seen(self, source_url: str, title: str, note_path: str = "") -> DedupCheckResult:
        now = datetime.now(UTC).isoformat()
        dedup_key, reason, normalized_url, host = self.build_key(source_url, title)
        title_norm = self.normalize_title(title)

        self._conn.execute(
            """
            INSERT INTO dedup_entries (
                dedup_key, source_url, title_norm, source_host,
                first_seen_at, last_seen_at, note_path, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(dedup_key) DO UPDATE SET
                source_url=excluded.source_url,
                title_norm=excluded.title_norm,
                source_host=excluded.source_host,
                last_seen_at=excluded.last_seen_at,
                note_path=CASE WHEN excluded.note_path <> '' THEN excluded.note_path ELSE dedup_entries.note_path END
            """,
            (dedup_key, normalized_url, title_norm, host, now, now, note_path),
        )

        return DedupCheckResult(
            exists=True,
            dedup_key=dedup_key,
            reason=reason,
            normalized_url=normalized_url,
            source_host=host,
        )

    def import_legacy_urls(self, urls: Iterable[str]) -> int:
        imported = 0
        now = datetime.now(UTC).isoformat()
        for url in urls:
            normalized_url, host = self.normalize_url(url)
            dedup_key = f"src:{normalized_url}" if normalized_url else ""
            if not dedup_key:
                continue
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO dedup_entries (
                    dedup_key, source_url, title_norm, source_host,
                    first_seen_at, last_seen_at, note_path, version
                ) VALUES (?, ?, '', ?, ?, ?, '', 1)
                """,
                (dedup_key, normalized_url, host, now, now),
            )
            imported += int(cur.rowcount > 0)
        return imported

    def set_kv(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO kv_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_kv(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return str(row[0])
