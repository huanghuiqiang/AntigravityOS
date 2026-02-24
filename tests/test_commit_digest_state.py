from __future__ import annotations

from pathlib import Path

from agents.daily_briefing.commit_digest_state import CommitDigestStateStore, DigestRunState


def test_state_store_success_lookup(tmp_path: Path) -> None:
    store = CommitDigestStateStore(tmp_path / "state.sqlite3")
    try:
        store.begin()
        store.record(
            DigestRunState(
                digest_key="k1",
                date="2026-02-24",
                timezone="Asia/Shanghai",
                repos="a/b",
                authors="*",
                status="success",
                trace_id="trace1",
                commit_count=3,
                chunk_count=1,
                error_message=None,
            ),
            force_send=False,
        )
        store.commit()
        assert store.is_success("k1") is True
        assert store.is_success("k2") is False
    finally:
        store.close()
