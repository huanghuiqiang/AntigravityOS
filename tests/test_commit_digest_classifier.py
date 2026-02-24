from __future__ import annotations

from datetime import UTC, datetime

from agents.daily_briefing import commit_digest
from agents.daily_briefing.commit_digest_renderer import CommitItem


def _item(message: str, files: tuple[str, ...] = ()) -> CommitItem:
    return CommitItem(
        repo="owner/repo",
        sha="abcdef123456",
        author="hugh",
        message=message,
        committed_at=datetime(2026, 2, 24, 10, 0, tzinfo=UTC),
        url="https://github.com/owner/repo/commit/abcdef1",
        files=files,
    )


def test_classify_by_prefix() -> None:
    assert commit_digest._classify_commit(_item("feat: add summary")) == "feat"


def test_classify_by_keyword() -> None:
    assert commit_digest._classify_commit(_item("hotfix login issue")) == "fix"


def test_classify_by_path_vote() -> None:
    result = commit_digest._classify_commit(_item("update pipeline", files=(".github/workflows/ci.yml",)))
    assert result == "ci"


def test_classify_mixed_when_scores_tie() -> None:
    result = commit_digest._classify_commit(
        _item("update", files=("docs/guide.md", "tests/test_a.py")),
    )
    assert result == "mixed"


def test_analyze_commits_counts_and_risk() -> None:
    commits = [
        _item("feat: add x", files=("scheduler.py",)),
        _item("fix: patch y"),
        _item("docs: update", files=("docs/readme.md",)),
    ]
    analytics = commit_digest._analyze_commits(
        commits=commits,
        exclude_types={"docs"},
        risk_paths=["scheduler.py"],
    )
    assert analytics.total_commits == 3
    assert analytics.effective_commits == 2
    assert analytics.high_risk_changes == 1
    assert analytics.category_counts["feat"] == 1
