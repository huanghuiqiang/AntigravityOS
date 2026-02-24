from __future__ import annotations

from datetime import UTC, datetime

from agents.daily_briefing.commit_digest_renderer import (
    CommitItem,
    build_feishu_post_payload,
    build_feishu_text_payload,
    build_markdown_chunks,
)


def _item(repo: str, sha: str, msg: str, minute: int) -> CommitItem:
    return CommitItem(
        repo=repo,
        sha=sha,
        author="hugh",
        message=msg,
        committed_at=datetime(2026, 2, 24, 10, minute, tzinfo=UTC),
        url=f"https://github.com/{repo}/commit/{sha}",
    )


def test_build_markdown_chunks_adds_prefix_and_index() -> None:
    commits = [_item("huanghuiqiang/AntigravityOS", "abcdef123", "feat: a", 1)]
    chunks = build_markdown_chunks(date_label="2026-02-24", timezone="Asia/Shanghai", commits=commits, max_chars=500)
    assert len(chunks) == 1
    assert chunks[0].startswith("【Commit日报】")
    assert "[1/1]" in chunks[0].splitlines()[0]


def test_build_markdown_chunks_splits_long_content() -> None:
    commits = [_item("repo/a", f"sha{i:03d}", f"feat: message {i}", i % 50) for i in range(80)]
    chunks = build_markdown_chunks(date_label="2026-02-24", timezone="Asia/Shanghai", commits=commits, max_chars=600)
    assert len(chunks) > 1
    assert chunks[0].splitlines()[0].endswith(f"[1/{len(chunks)}]")


def test_build_payloads() -> None:
    post = build_feishu_post_payload("t", "line1\nline2")
    text = build_feishu_text_payload("abc")
    assert post["msg_type"] == "post"
    assert text["msg_type"] == "text"
