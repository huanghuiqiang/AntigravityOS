from __future__ import annotations

from pathlib import Path

from agos.dedup_store import DedupStore


def test_upsert_and_check(tmp_path: Path) -> None:
    db = tmp_path / "dedup.sqlite3"
    store = DedupStore(db)
    try:
        store.begin()
        check0 = store.check("https://example.com/a?utm_source=x", "Article")
        assert check0.exists is False

        store.upsert_seen("https://example.com/a?utm_source=x", "Article", note_path="/tmp/a.md")
        check1 = store.check("https://example.com/a?utm_source=y", "Article")
        assert check1.exists is True
        assert check1.reason == "same_source"
        store.commit()
    finally:
        store.close()


def test_import_legacy_urls(tmp_path: Path) -> None:
    db = tmp_path / "dedup.sqlite3"
    store = DedupStore(db)
    try:
        store.begin()
        imported = store.import_legacy_urls([
            "https://example.com/a?utm_source=x",
            "https://example.com/a?utm_source=y",
            "",
        ])
        store.commit()
        assert imported == 1
    finally:
        store.close()
