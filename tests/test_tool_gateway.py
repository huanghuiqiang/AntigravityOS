from __future__ import annotations

from datetime import datetime, timedelta, UTC

import pytest

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover
    TestClient = None

from apps.tool_gateway import main as gateway_main
from apps.tool_gateway.github_service import GitHubService


@pytest.fixture(autouse=True)
def _reset_service(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway_main._github_service = None
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")


def test_health_endpoint_returns_trace() -> None:
    if TestClient is None:
        pytest.skip("fastapi not installed")
    client = TestClient(gateway_main.app)
    response = client.post("/api/tools/health", headers={"X-Trace-Id": "trace-a"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["trace_id"] == "trace-a"


def test_unknown_tool_returns_404() -> None:
    if TestClient is None:
        pytest.skip("fastapi not installed")
    client = TestClient(gateway_main.app)
    response = client.post("/api/tools/not_exists", json={})
    assert response.status_code == 404
    payload = response.json()
    assert payload["success"] is False
    assert "tool not found" in payload["error"]["message"]


def test_github_comment_pr_dry_run() -> None:
    if TestClient is None:
        pytest.skip("fastapi not installed")

    async def fake_comment_pr(
        self: GitHubService,
        *,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        dry_run: bool,
    ) -> dict[str, object]:
        return {
            "dry_run": dry_run,
            "external_id": f"{owner}/{repo}#{pr_number}",
            "body": body,
        }

    client = TestClient(gateway_main.app)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(GitHubService, "comment_pr", fake_comment_pr)

    response = client.post(
        "/api/tools/github_comment_pr",
        json={
            "owner": "openclaw",
            "repo": "openclaw",
            "prNumber": 1,
            "body": "hello",
            "dryRun": True,
        },
        headers={"X-Trace-Id": "trace-comment"},
    )
    monkeypatch.undo()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["trace_id"] == "trace-comment"


def test_commit_stats_validation_error() -> None:
    if TestClient is None:
        pytest.skip("fastapi not installed")

    client = TestClient(gateway_main.app)
    now = datetime.now(UTC)
    response = client.post(
        "/api/tools/github_commit_stats",
        json={
            "owner": "openclaw",
            "repo": "openclaw",
            "since": now.isoformat(),
            "until": (now - timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert "until must be greater than since" in payload["error"]["message"]


def test_internal_action_accepts_minimal_payload() -> None:
    if TestClient is None:
        pytest.skip("fastapi not installed")
    client = TestClient(gateway_main.app)

    response = client.post("/api/tools/ag_daily_briefing", json={"dryRun": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["dry_run"] is True
