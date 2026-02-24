from __future__ import annotations

import asyncio
import argparse
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agos.config import (
    commit_digest_alert_on_failure,
    commit_digest_authors,
    commit_digest_dry_run,
    commit_digest_enabled,
    commit_digest_force_send,
    commit_digest_max_retries,
    commit_digest_repos,
    commit_digest_retry_backoff_sec,
    commit_digest_state_db_file,
    commit_digest_timezone,
    feishu_bot_msg_type,
    feishu_bot_secret,
    feishu_bot_webhook,
)
from agos.notify import send_message
from apps.tool_gateway.github_service import GitHubService, ToolGatewayError
from agents.daily_briefing.commit_digest_renderer import (
    CommitItem,
    build_feishu_post_payload,
    build_feishu_text_payload,
    build_markdown_chunks,
    build_summary_text,
)
from agents.daily_briefing.commit_digest_state import CommitDigestStateStore, DigestRunState
from skills.feishu_bot_sender import FeishuBotSendError, send_feishu_webhook


@dataclass(frozen=True)
class TimeWindow:
    since: datetime
    until: datetime
    date_label: str
    timezone: str


def _trace_id() -> str:
    return uuid.uuid4().hex[:12]


def _resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _today_window(timezone_name: str) -> TimeWindow:
    tz = _resolve_timezone(timezone_name)
    now = datetime.now(tz)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return TimeWindow(
        since=since.astimezone(UTC),
        until=now.astimezone(UTC),
        date_label=now.strftime("%Y-%m-%d"),
        timezone=timezone_name,
    )


def _digest_key(window: TimeWindow, repos: list[str], authors: list[str]) -> str:
    repos_key = ",".join(sorted(repos))
    authors_key = ",".join(sorted(authors)) if authors else "*"
    return f"{window.date_label}|{window.timezone}|repo:{repos_key}|authors:{authors_key}"


def _parse_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError(f"invalid repo format: {repo}, expected owner/repo")
    owner, name = repo.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        raise ValueError(f"invalid repo format: {repo}, expected owner/repo")
    return owner, name


def _normalize_message(raw: object) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "(no message)"


def _commit_item_from_payload(repo: str, payload: dict[str, object]) -> CommitItem | None:
    sha = payload.get("sha")
    html_url = payload.get("html_url")
    commit_data = payload.get("commit")
    if not isinstance(sha, str) or not isinstance(html_url, str) or not isinstance(commit_data, dict):
        return None

    message = _normalize_message(commit_data.get("message"))
    author_name = "unknown"
    commit_author = commit_data.get("author")
    if isinstance(commit_author, dict):
        name = commit_author.get("name")
        date_text = commit_author.get("date")
    else:
        name = None
        date_text = None

    if isinstance(name, str) and name.strip():
        author_name = name.strip()

    committed_at = None
    if isinstance(date_text, str) and date_text.strip():
        try:
            committed_at = datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            committed_at = None
    if committed_at is None:
        return None

    return CommitItem(
        repo=repo,
        sha=sha,
        author=author_name,
        message=message,
        committed_at=committed_at,
        url=html_url,
    )


async def _collect_commits_async(
    *,
    service: GitHubService,
    repos: list[str],
    authors: list[str],
    since: datetime,
    until: datetime,
) -> list[CommitItem]:
    wanted_authors = {a.strip().lower() for a in authors if a.strip()}
    all_items: list[CommitItem] = []

    for repo in repos:
        owner, repo_name = _parse_repo(repo)
        raw = await service._request(
            method="GET",
            path=f"/repos/{owner}/{repo_name}/commits",
            params={
                "since": since.isoformat(),
                "until": until.isoformat(),
                "per_page": "100",
            },
        )
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            parsed = _commit_item_from_payload(repo, item)
            if parsed is None:
                continue
            if wanted_authors and parsed.author.lower() not in wanted_authors:
                continue
            all_items.append(parsed)

    all_items.sort(key=lambda x: x.committed_at)
    return all_items


def _collect_commits(
    *,
    service: GitHubService,
    repos: list[str],
    authors: list[str],
    since: datetime,
    until: datetime,
) -> list[CommitItem]:
    return asyncio.run(
        _collect_commits_async(
            service=service,
            repos=repos,
            authors=authors,
            since=since,
            until=until,
        )
    )


def _send_with_retry(
    *,
    webhook: str,
    secret: str,
    payload: dict[str, object],
    max_retries: int,
    backoff_sec: int,
    trace_id: str,
) -> None:
    last_error: Exception | None = None
    for idx in range(max_retries + 1):
        try:
            send_feishu_webhook(webhook=webhook, payload=payload, secret=secret)
            return
        except Exception as exc:
            last_error = exc
            if idx >= max_retries:
                break
            sleep_sec = backoff_sec * (2 ** idx)
            print(f"[commit-digest] trace_id={trace_id} retry={idx+1} sleep={sleep_sec}s error={exc}")
            time.sleep(sleep_sec)
    raise RuntimeError(f"send webhook failed after retries: {last_error}")


def _send_failure_alert(*, trace_id: str, error: str, digest_key: str) -> None:
    if not commit_digest_alert_on_failure():
        return
    text = (
        "🚨 <b>Commit Digest 任务失败</b>\n"
        f"trace_id: <code>{trace_id}</code>\n"
        f"digest_key: <code>{digest_key}</code>\n"
        f"error: <code>{error[:500]}</code>"
    )
    send_message(text)


def run_commit_digest(*, dry_run: bool = False, force_send_override: bool | None = None) -> int:
    if not commit_digest_enabled():
        print("[commit-digest] disabled by COMMIT_DIGEST_ENABLED")
        return 0

    webhook = feishu_bot_webhook()
    if not webhook:
        print("[commit-digest] FEISHU_BOT_WEBHOOK 未配置")
        return 1

    github_token = os.getenv("GITHUB_TOKEN", "").strip()
    if not github_token:
        print("[commit-digest] GITHUB_TOKEN 未配置")
        return 1

    started = time.perf_counter()
    trace_id = _trace_id()
    repos = commit_digest_repos()
    authors = commit_digest_authors()
    timezone_name = commit_digest_timezone()
    window = _today_window(timezone_name)
    digest_key = _digest_key(window, repos, authors)

    store = CommitDigestStateStore(commit_digest_state_db_file())
    try:
        force_send = commit_digest_force_send() if force_send_override is None else force_send_override
        if store.is_success(digest_key) and not force_send:
            store.begin()
            store.record(
                DigestRunState(
                    digest_key=digest_key,
                    date=window.date_label,
                    timezone=window.timezone,
                    repos=",".join(repos),
                    authors=",".join(authors) if authors else "*",
                    status="skipped",
                    trace_id=trace_id,
                    commit_count=0,
                    chunk_count=0,
                    error_message=None,
                ),
                force_send=force_send,
            )
            store.commit()
            print(f"[commit-digest] skipped, already sent digest_key={digest_key}")
            return 0

        service = GitHubService(token=github_token)
        commits = _collect_commits(
            service=service,
            repos=repos,
            authors=authors,
            since=window.since,
            until=window.until,
        )

        chunks = build_markdown_chunks(
            date_label=window.date_label,
            timezone=window.timezone,
            commits=commits,
        )

        msg_type = feishu_bot_msg_type()
        secret = feishu_bot_secret()
        chunk_count = len(chunks)
        if dry_run:
            print(f"[commit-digest] dry-run trace_id={trace_id} chunks={chunk_count} commits={len(commits)}")
            print(chunks[0][:1000] if chunks else "(empty)")
            store.begin()
            store.record(
                DigestRunState(
                    digest_key=digest_key,
                    date=window.date_label,
                    timezone=window.timezone,
                    repos=",".join(repos),
                    authors=",".join(authors) if authors else "*",
                    status="skipped",
                    trace_id=trace_id,
                    commit_count=len(commits),
                    chunk_count=chunk_count,
                    error_message="dry-run",
                ),
                force_send=force_send,
            )
            store.commit()
            return 0

        for idx, chunk in enumerate(chunks, 1):
            if msg_type == "text":
                payload: dict[str, object] = build_feishu_text_payload(chunk)
            else:
                title = f"【Commit日报】每日 Commit 日报（{window.date_label}）[{idx}/{len(chunks)}]"
                payload = build_feishu_post_payload(title, chunk)
            _send_with_retry(
                webhook=webhook,
                secret=secret,
                payload=payload,
                max_retries=commit_digest_max_retries(),
                backoff_sec=commit_digest_retry_backoff_sec(),
                trace_id=trace_id,
            )

        summary = build_summary_text(date_label=window.date_label, timezone=window.timezone, commits=commits)
        _send_with_retry(
            webhook=webhook,
            secret=secret,
            payload=build_feishu_text_payload(summary),
            max_retries=commit_digest_max_retries(),
            backoff_sec=commit_digest_retry_backoff_sec(),
            trace_id=trace_id,
        )

        store.begin()
        store.record(
            DigestRunState(
                digest_key=digest_key,
                date=window.date_label,
                timezone=window.timezone,
                repos=",".join(repos),
                authors=",".join(authors) if authors else "*",
                status="success",
                trace_id=trace_id,
                commit_count=len(commits),
                chunk_count=chunk_count + 1,
                error_message=None,
            ),
            force_send=force_send,
        )
        store.commit()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        print(
            "[commit-digest] success "
            f"trace_id={trace_id} commits={len(commits)} chunks={chunk_count + 1} latency_ms={elapsed_ms}"
        )
        return 0

    except (ValueError, ToolGatewayError, FeishuBotSendError, RuntimeError) as exc:
        store.rollback()
        store.begin()
        store.record(
            DigestRunState(
                digest_key=digest_key,
                date=window.date_label,
                timezone=window.timezone,
                repos=",".join(repos),
                authors=",".join(authors) if authors else "*",
                status="failed",
                trace_id=trace_id,
                commit_count=0,
                chunk_count=0,
                error_message=str(exc),
            ),
            force_send=commit_digest_force_send() if force_send_override is None else force_send_override,
        )
        store.commit()
        if store.recent_failures(limit=2) == 2:
            _send_failure_alert(trace_id=trace_id, error=str(exc), digest_key=digest_key)
        print(f"[commit-digest] failed trace_id={trace_id} error={exc}")
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-send", action="store_true")
    args = parser.parse_args()
    raise SystemExit(
        run_commit_digest(
            dry_run=args.dry_run or commit_digest_dry_run(),
            force_send_override=True if args.force_send else None,
        )
    )
