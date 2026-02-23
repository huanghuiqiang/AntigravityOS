from __future__ import annotations

import httpx
import pytest
import asyncio

from apps.tool_gateway.github_service import GitHubService, ToolGatewayError


def test_list_open_prs_retries_on_429_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 3:
            return httpx.Response(429, json={"message": "rate limited"})
        return httpx.Response(200, json=[{"number": 1, "title": "T", "html_url": "u", "state": "open"}])

    service = GitHubService(token="x", base_url="https://api.github.com", retry_delay_seconds=0)

    async def fake_request(
        self: GitHubService,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> dict[str, object] | list[dict[str, object]]:
        response = handler(httpx.Request(method=method, url=f"https://api.github.com{path}"))
        if response.status_code >= 400:
            if response.status_code == 429 and calls["count"] <= self.max_retries:
                return await fake_request(self, method=method, path=path, params=params, json_body=json_body)
            raise ToolGatewayError("rate limited", status_code=response.status_code)
        payload = response.json()
        assert isinstance(payload, list)
        return payload

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(GitHubService, "_request", fake_request)
    result = asyncio.run(service.list_open_prs(owner="o", repo="r", per_page=10))
    monkeypatch.undo()

    assert result["count"] == 1
    assert calls["count"] == 3


def test_comment_pr_dry_run_has_no_side_effect() -> None:
    service = GitHubService(token="x")
    result = asyncio.run(service.comment_pr(owner="o", repo="r", pr_number=7, body="hello", dry_run=True))
    assert result["dry_run"] is True
    assert result["external_id"] == "o/r#7"
