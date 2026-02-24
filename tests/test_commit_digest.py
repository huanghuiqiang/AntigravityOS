from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agents.daily_briefing import commit_digest
from agents.daily_briefing.commit_digest_renderer import CommitItem


def test_run_commit_digest_requires_webhook(monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_DIGEST_ENABLED", "true")
    monkeypatch.delenv("FEISHU_BOT_WEBHOOK", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert commit_digest.run_commit_digest() == 1


def test_run_commit_digest_skip_when_already_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_DIGEST_ENABLED", "true")
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("COMMIT_DIGEST_REPOS", "owner/repo")
    monkeypatch.setenv("COMMIT_DIGEST_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("FORCE_SEND", "false")

    db_path = tmp_path / "digest.sqlite3"
    monkeypatch.setattr(commit_digest, "commit_digest_state_db_file", lambda: db_path)
    monkeypatch.setattr(commit_digest, "_collect_commits", lambda **kwargs: [])
    monkeypatch.setattr(commit_digest, "_send_with_retry", lambda **kwargs: None)

    assert commit_digest.run_commit_digest() == 0
    assert commit_digest.run_commit_digest() == 0


def test_run_commit_digest_dry_run_does_not_send(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("COMMIT_DIGEST_ENABLED", "true")
    monkeypatch.setenv("FEISHU_BOT_WEBHOOK", "https://open.feishu.cn/open-apis/bot/v2/hook/x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("COMMIT_DIGEST_REPOS", "owner/repo")

    db_path = tmp_path / "digest.sqlite3"
    monkeypatch.setattr(commit_digest, "commit_digest_state_db_file", lambda: db_path)
    monkeypatch.setattr(
        commit_digest,
        "_collect_commits",
        lambda **kwargs: [
            CommitItem(
                repo="owner/repo",
                sha="abc1234",
                author="hugh",
                message="feat: x",
                committed_at=datetime(2026, 2, 24, 10, 0, tzinfo=UTC),
                url="https://github.com/owner/repo/commit/abc1234",
            )
        ],
    )
    monkeypatch.setattr(
        commit_digest,
        "_send_with_retry",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not send in dry-run")),
    )

    assert commit_digest.run_commit_digest(dry_run=True) == 0
