from __future__ import annotations

from datetime import UTC, datetime

from agents.daily_briefing.commit_digest_renderer import (
    CommitDigestAnalytics,
    CommitItem,
    build_feishu_post_payload,
    build_feishu_text_payload,
    build_markdown_chunks,
    build_summary_text,
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


def test_build_markdown_chunks_with_analytics() -> None:
    commits = [_item("huanghuiqiang/AntigravityOS", "abcdef123", "feat: a", 1)]
    analytics = CommitDigestAnalytics(
        total_commits=1,
        effective_commits=1,
        category_counts={"feat": 1},
        high_risk_changes=0,
        revert_count=0,
        conclusion="今天以功能推进为主，风险较低。",
    )
    chunks = build_markdown_chunks(
        date_label="2026-02-24",
        timezone="Asia/Shanghai",
        commits=commits,
        analytics=analytics,
        max_chars=500,
    )
    assert "Top 类别" in chunks[0]
    assert "分类明细" in chunks[0]
    assert "风险提示" in chunks[0]


def test_build_markdown_chunks_compact_fallback() -> None:
    commits = [_item("repo/a", f"sha{i:03d}", f"feat: m{i}", i % 50) for i in range(20)]
    analytics = CommitDigestAnalytics(
        total_commits=20,
        effective_commits=20,
        category_counts={"feat": 20},
        high_risk_changes=0,
        revert_count=0,
        conclusion="x" * 200,
    )
    chunks = build_markdown_chunks(
        date_label="2026-02-24",
        timezone="Asia/Shanghai",
        commits=commits,
        analytics=analytics,
        max_chars=120,
    )
    assert chunks
    assert chunks[0].startswith("【Commit日报】")


def test_build_summary_text_with_analytics() -> None:
    analytics = CommitDigestAnalytics(
        total_commits=7,
        effective_commits=6,
        category_counts={"feat": 3, "fix": 2},
        high_risk_changes=1,
        revert_count=0,
        conclusion="今天以功能推进为主，风险较低。",
    )
    summary = build_summary_text(
        date_label="2026-02-24",
        timezone="Asia/Shanghai",
        commits=[],
        analytics=analytics,
    )
    assert "总提交：7" in summary
    assert "Top 类别" in summary
