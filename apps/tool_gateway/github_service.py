"""GitHub API service for tool gateway."""

from __future__ import annotations

import hashlib
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping

import httpx


class ToolGatewayError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(slots=True)
class GitHubService:
    token: str
    base_url: str = "https://api.github.com"
    timeout_seconds: float = 15.0
    max_retries: int = 2
    retry_delay_seconds: float = 0.2

    async def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> dict[str, object] | list[dict[str, object]]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        url = f"{self.base_url}{path}"
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method, url, headers=headers, params=params, json=json_body)

            retryable = method == "GET" and response.status_code in {429, 500, 502, 503, 504}
            if not retryable or attempt >= self.max_retries:
                break
            await asyncio.sleep(self.retry_delay_seconds * (attempt + 1))

        if response is None:
            raise ToolGatewayError("GitHub request failed before response", status_code=502)

        if response.status_code >= 400:
            message = self._build_error_message(response)
            raise ToolGatewayError(message=message, status_code=response.status_code)

        payload = response.json()
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            normalized: list[dict[str, object]] = []
            for item in payload:
                if isinstance(item, dict):
                    normalized.append(item)
            return normalized
        raise ToolGatewayError("GitHub returned unsupported payload", status_code=502)

    @staticmethod
    def _build_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = payload.get("message")
                if isinstance(message, str) and message:
                    return message
        except ValueError:
            pass
        return f"GitHub API status={response.status_code}"

    @staticmethod
    def hash_input(payload: Mapping[str, object]) -> str:
        raw = repr(sorted(payload.items())).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    async def list_open_prs(self, *, owner: str, repo: str, per_page: int) -> dict[str, object]:
        response = await self._request(
            method="GET",
            path=f"/repos/{owner}/{repo}/pulls",
            params={"state": "open", "per_page": str(per_page)},
        )
        if not isinstance(response, list):
            raise ToolGatewayError("GitHub returned invalid pull list payload", status_code=502)

        items: list[dict[str, object]] = []
        for item in response:
            number = item.get("number")
            title = item.get("title")
            html_url = item.get("html_url")
            state = item.get("state")
            if isinstance(number, int) and isinstance(title, str):
                items.append(
                    {
                        "number": number,
                        "title": title,
                        "url": html_url if isinstance(html_url, str) else "",
                        "state": state if isinstance(state, str) else "",
                    }
                )
        return {"items": items, "count": len(items)}

    async def commit_stats(
        self,
        *,
        owner: str,
        repo: str,
        since: datetime,
        until: datetime,
    ) -> dict[str, object]:
        response = await self._request(
            method="GET",
            path=f"/repos/{owner}/{repo}/commits",
            params={
                "since": since.astimezone(UTC).isoformat(),
                "until": until.astimezone(UTC).isoformat(),
                "per_page": "100",
            },
        )
        if not isinstance(response, list):
            raise ToolGatewayError("GitHub returned invalid commits payload", status_code=502)

        authors: set[str] = set()
        for commit in response:
            author = commit.get("author")
            if isinstance(author, dict):
                login = author.get("login")
                if isinstance(login, str) and login:
                    authors.add(login)
                    continue
            commit_block = commit.get("commit")
            if isinstance(commit_block, dict):
                commit_author = commit_block.get("author")
                if isinstance(commit_author, dict):
                    name = commit_author.get("name")
                    if isinstance(name, str) and name:
                        authors.add(name)
        return {
            "total": len(response),
            "authors": sorted(authors),
            "since": since.astimezone(UTC).isoformat(),
            "until": until.astimezone(UTC).isoformat(),
        }

    async def repo_activity(self, *, owner: str, repo: str, hours: int) -> dict[str, object]:
        until = datetime.now(UTC)
        since = until - timedelta(hours=hours)
        stats = await self.commit_stats(owner=owner, repo=repo, since=since, until=until)
        return {
            "hours": hours,
            "commit_total": stats.get("total", 0),
            "authors": stats.get("authors", []),
            "window_start": stats.get("since", ""),
            "window_end": stats.get("until", ""),
        }

    async def comment_pr(
        self,
        *,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        dry_run: bool,
    ) -> dict[str, object]:
        if dry_run:
            return {
                "dry_run": True,
                "message": "dry run enabled, comment not sent",
                "external_id": f"{owner}/{repo}#{pr_number}",
            }

        payload = {"body": body}
        response = await self._request(
            method="POST",
            path=f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json_body=payload,
        )
        if not isinstance(response, dict):
            raise ToolGatewayError("GitHub returned invalid comment payload", status_code=502)
        comment_id = response.get("id")
        html_url = response.get("html_url")
        return {
            "dry_run": False,
            "comment_id": comment_id if isinstance(comment_id, int) else 0,
            "url": html_url if isinstance(html_url, str) else "",
            "external_id": f"{owner}/{repo}#{pr_number}",
        }
