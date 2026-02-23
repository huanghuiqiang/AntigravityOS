"""FastAPI app for tool gateway."""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC
from collections import deque

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from apps.tool_gateway.audit import audit_event
from apps.tool_gateway.github_service import GitHubService, ToolGatewayError
from apps.tool_gateway.schemas import (
    GithubCommentPrRequest,
    GithubCommitStatsRequest,
    GithubListOpenPrsRequest,
    GithubRepoActivityRequest,
    InternalActionRequest,
    ToolError,
    ToolEnvelope,
)

app = FastAPI(title="Antigravity Tool Gateway", version="1.0.0")

_ALLOWED_TOOLS = {
    "github_list_open_prs",
    "github_commit_stats",
    "github_repo_activity",
    "github_comment_pr",
    "ag_daily_briefing",
    "ag_weekly_sync",
}

_github_service: GitHubService | None = None
_REQUEST_COUNT: dict[str, int] = {}
_ERROR_COUNT: dict[str, int] = {}
_LATENCY_MS: deque[int] = deque(maxlen=200)
_ACTOR_WINDOWS: dict[str, deque[float]] = {}
_RATE_LIMIT_PER_MINUTE = 60


def _trace_id(incoming: str | None) -> str:
    if incoming and incoming.strip():
        return incoming.strip()
    return str(uuid.uuid4())


def _service() -> GitHubService:
    global _github_service
    if _github_service is None:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise HTTPException(status_code=500, detail="GITHUB_TOKEN not configured")
        _github_service = GitHubService(token=token)
    return _github_service


def _rate_limited(actor: str, now: float) -> bool:
    window = _ACTOR_WINDOWS.get(actor)
    if window is None:
        window = deque()
        _ACTOR_WINDOWS[actor] = window
    cutoff = now - 60.0
    while window and window[0] < cutoff:
        window.popleft()
    if len(window) >= _RATE_LIMIT_PER_MINUTE:
        return True
    window.append(now)
    return False


def _response(
    *,
    trace_id: str,
    data: dict[str, object] | None = None,
    error_message: str | None = None,
    status_code: int = 200,
) -> JSONResponse:
    envelope = ToolEnvelope(
        success=status_code < 400,
        data=data,
        error=None if status_code < 400 else ToolError(message=error_message or "request failed"),
        trace_id=trace_id,
        content=[{"type": "text", "text": str(data)}] if status_code < 400 and data is not None else None,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


@app.post("/api/tools/health")
async def tools_health(x_trace_id: str | None = Header(default=None, alias="X-Trace-Id")) -> JSONResponse:
    trace_id = _trace_id(x_trace_id)
    latencies = list(_LATENCY_MS)
    p50 = 0 if not latencies else sorted(latencies)[len(latencies) // 2]
    p95 = 0 if not latencies else sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)]
    return _response(
        trace_id=trace_id,
        data={
            "ok": True,
            "service": "tool_gateway",
            "request_count": _REQUEST_COUNT,
            "error_count": _ERROR_COUNT,
            "latency_ms_p50": p50,
            "latency_ms_p95": p95,
        },
    )


@app.post("/api/tools/{tool_name}")
async def invoke_tool(
    tool_name: str,
    request: Request,
    x_trace_id: str | None = Header(default=None, alias="X-Trace-Id"),
) -> JSONResponse:
    trace_id = _trace_id(x_trace_id)
    start = time.perf_counter()
    actor = request.headers.get("X-Actor", "openclaw")
    now = time.time()

    if _rate_limited(actor, now):
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        return _response(trace_id=trace_id, status_code=429, error_message="rate limit exceeded")

    if tool_name not in _ALLOWED_TOOLS:
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        return _response(trace_id=trace_id, status_code=404, error_message=f"tool not found: {tool_name}")

    body = await request.json()
    if not isinstance(body, dict):
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        return _response(trace_id=trace_id, status_code=400, error_message="request body must be a JSON object")

    try:
        if tool_name == "github_list_open_prs":
            svc = _service()
            list_request = GithubListOpenPrsRequest.model_validate(body)
            data = await svc.list_open_prs(owner=list_request.owner, repo=list_request.repo, per_page=list_request.per_page)
        elif tool_name == "github_commit_stats":
            svc = _service()
            stats_request = GithubCommitStatsRequest.model_validate(body)
            data = await svc.commit_stats(
                owner=stats_request.owner,
                repo=stats_request.repo,
                since=stats_request.since.replace(tzinfo=UTC),
                until=stats_request.until.replace(tzinfo=UTC),
            )
        elif tool_name == "github_repo_activity":
            svc = _service()
            activity_request = GithubRepoActivityRequest.model_validate(body)
            data = await svc.repo_activity(owner=activity_request.owner, repo=activity_request.repo, hours=activity_request.hours)
        elif tool_name == "github_comment_pr":
            svc = _service()
            comment_request = GithubCommentPrRequest.model_validate(body)
            data = await svc.comment_pr(
                owner=comment_request.owner,
                repo=comment_request.repo,
                pr_number=comment_request.prNumber,
                body=comment_request.body,
                dry_run=comment_request.dryRun,
            )
        elif tool_name == "ag_daily_briefing":
            action_request = InternalActionRequest.model_validate(body)
            data = {
                "dry_run": action_request.dryRun,
                "message": "daily briefing dispatched" if not action_request.dryRun else "daily briefing dry run",
                "section_title": action_request.section_title or "每日进度日志",
                "document_id": action_request.document_id or "",
            }
        else:
            action_request = InternalActionRequest.model_validate(body)
            data = {
                "dry_run": action_request.dryRun,
                "message": "weekly sync dispatched" if not action_request.dryRun else "weekly sync dry run",
                "section_title": action_request.section_title or "5. 周报 & 复盘区（留空，Claude以后生成）",
                "document_id": action_request.document_id or "",
            }

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        _LATENCY_MS.append(elapsed_ms)
        _REQUEST_COUNT[tool_name] = _REQUEST_COUNT.get(tool_name, 0) + 1
        data["elapsed_ms"] = elapsed_ms
        input_hash = GitHubService.hash_input(body)
        audit_event(
            trace_id=trace_id,
            tool_name=tool_name,
            actor=actor,
            result="success",
            external_id=str(data.get("external_id", "")) if data.get("external_id") is not None else None,
            input_hash=input_hash,
        )
        return _response(trace_id=trace_id, data=data)

    except ToolGatewayError as exc:
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        audit_event(trace_id=trace_id, tool_name=tool_name, actor=actor, result="error", external_id=None, input_hash=None)
        return _response(trace_id=trace_id, status_code=exc.status_code, error_message=exc.message)
    except ValueError as exc:
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        audit_event(trace_id=trace_id, tool_name=tool_name, actor=actor, result="error", external_id=None, input_hash=None)
        return _response(trace_id=trace_id, status_code=400, error_message=str(exc))
    except HTTPException as exc:
        _ERROR_COUNT[tool_name] = _ERROR_COUNT.get(tool_name, 0) + 1
        message = str(exc.detail)
        return _response(trace_id=trace_id, status_code=exc.status_code, error_message=message)
