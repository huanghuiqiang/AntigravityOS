from __future__ import annotations

import asyncio
import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from agos.config import (
    commit_digest_alert_on_failure,
    commit_digest_authors,
    commit_digest_dry_run,
    commit_digest_enabled,
    commit_digest_exclude_types,
    commit_digest_force_send,
    commit_digest_include_categories,
    commit_digest_include_risk,
    commit_digest_max_classify_commits,
    commit_digest_max_report_commits,
    commit_digest_max_retries,
    commit_digest_repos,
    commit_digest_risk_paths,
    commit_digest_retry_backoff_sec,
    commit_digest_state_db_file,
    commit_digest_timezone,
    feishu_bot_msg_type,
    feishu_bot_secret,
    feishu_bot_webhook,
    state_dir,
)
from agos.notify import send_message
from apps.tool_gateway.github_service import GitHubService, ToolGatewayError
from agents.daily_briefing.commit_digest_renderer import (
    CommitItem,
    CommitDigestAnalytics,
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


class _GitHubRequester(Protocol):
    async def _request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, object] | list[dict[str, object]]:
        ...


_CATEGORY_ORDER = ["revert", "feat", "fix", "refactor", "test", "docs", "ci", "perf", "chore", "mixed"]
_PREFIX_TO_CATEGORY = {
    "revert": "revert",
    "feat": "feat",
    "fix": "fix",
    "refactor": "refactor",
    "test": "test",
    "docs": "docs",
    "ci": "ci",
    "perf": "perf",
    "chore": "chore",
}
_KEYWORD_TO_CATEGORY = {
    "bug": "fix",
    "hotfix": "fix",
    "fix": "fix",
    "feature": "feat",
    "readme": "docs",
    "doc": "docs",
    "test": "test",
    "workflow": "ci",
    "pipeline": "ci",
    "refactor": "refactor",
    "perf": "perf",
    "performance": "perf",
    "revert": "revert",
}
_PATH_RULES: list[tuple[str, str]] = [
    ("tests/", "test"),
    (".github/workflows/", "ci"),
    ("docs/", "docs"),
    ("readme", "docs"),
    ("docker-compose.yml", "chore"),
    ("dockerfile", "chore"),
]


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


def _extract_commit_prefix(message: str) -> str:
    first_line = message.splitlines()[0].strip().lower()
    if ":" not in first_line:
        return ""
    head = first_line.split(":", 1)[0]
    if "(" in head:
        head = head.split("(", 1)[0]
    head = head.replace("!", "").strip()
    return head


def _classify_commit(item: CommitItem) -> str:
    prefix = _extract_commit_prefix(item.message)
    if prefix in _PREFIX_TO_CATEGORY:
        return _PREFIX_TO_CATEGORY[prefix]

    scores: dict[str, int] = {}
    message_lower = item.message.lower()
    for token, category in _KEYWORD_TO_CATEGORY.items():
        if token in message_lower:
            scores[category] = scores.get(category, 0) + 2

    for changed in item.files:
        changed_lower = changed.lower()
        for prefix_rule, category in _PATH_RULES:
            if changed_lower.startswith(prefix_rule) or prefix_rule in changed_lower:
                scores[category] = scores.get(category, 0) + 1

    if not scores:
        return "chore"

    top_score = max(scores.values())
    top_categories = [name for name, score in scores.items() if score == top_score]
    if len(top_categories) > 1:
        return "mixed"
    return top_categories[0]


def _is_high_risk_change(item: CommitItem, risk_paths: list[str]) -> bool:
    if not item.files:
        return False
    for file_path in item.files:
        for prefix in risk_paths:
            if file_path.startswith(prefix):
                return True
    return False


def _build_conclusion(
    *,
    category_counts: dict[str, int],
    high_risk_changes: int,
    total_commits: int,
) -> str:
    if total_commits == 0:
        return "今日无提交，保持基线稳定。"
    feat = category_counts.get("feat", 0)
    fix = category_counts.get("fix", 0)
    if feat > fix and high_risk_changes == 0:
        return "今天以功能推进为主，风险较低。"
    if fix >= feat and fix > 0:
        return "今天以修复与稳定化为主，建议关注回归验证。"
    if high_risk_changes > 0:
        return "存在关键路径改动，建议重点复核。"
    return "提交结构均衡，整体风险可控。"


def _analyze_commits(
    *,
    commits: list[CommitItem],
    exclude_types: set[str],
    risk_paths: list[str],
) -> CommitDigestAnalytics:
    category_counts: dict[str, int] = {}
    high_risk_changes = 0
    effective_commits = 0
    revert_count = 0

    for item in commits:
        category = _classify_commit(item)
        category_counts[category] = category_counts.get(category, 0) + 1
        if category == "revert":
            revert_count += 1
        if category not in exclude_types:
            effective_commits += 1
        if _is_high_risk_change(item, risk_paths):
            high_risk_changes += 1

    ordered_counts: dict[str, int] = {}
    for name in _CATEGORY_ORDER:
        if name in category_counts:
            ordered_counts[name] = category_counts[name]
    for name, count in sorted(category_counts.items()):
        if name not in ordered_counts:
            ordered_counts[name] = count

    return CommitDigestAnalytics(
        total_commits=len(commits),
        effective_commits=effective_commits,
        category_counts=ordered_counts,
        high_risk_changes=high_risk_changes,
        revert_count=revert_count,
        conclusion=_build_conclusion(
            category_counts=category_counts,
            high_risk_changes=high_risk_changes,
            total_commits=len(commits),
        ),
    )


async def _fetch_changed_files(
    *,
    service: _GitHubRequester,
    owner: str,
    repo_name: str,
    sha: str,
) -> tuple[str, ...]:
    raw = await service._request(
        method="GET",
        path=f"/repos/{owner}/{repo_name}/commits/{sha}",
    )
    if not isinstance(raw, dict):
        return ()
    files_obj = raw.get("files")
    if not isinstance(files_obj, list):
        return ()
    out: list[str] = []
    for file_obj in files_obj:
        if not isinstance(file_obj, dict):
            continue
        filename = file_obj.get("filename")
        if isinstance(filename, str) and filename.strip():
            out.append(filename.strip())
    return tuple(out)


async def _collect_commits_async(
    *,
    service: _GitHubRequester,
    repos: list[str],
    authors: list[str],
    since: datetime,
    until: datetime,
    include_changed_files: bool,
    max_detail_commits: int,
    max_total_commits: int,
) -> list[CommitItem]:
    wanted_authors = {a.strip().lower() for a in authors if a.strip()}
    all_items: list[CommitItem] = []
    detail_budget = max(0, max_detail_commits)

    for repo in repos:
        owner, repo_name = _parse_repo(repo)
        page = 1
        while len(all_items) < max_total_commits:
            raw = await service._request(
                method="GET",
                path=f"/repos/{owner}/{repo_name}/commits",
                params={
                    "since": since.isoformat(),
                    "until": until.isoformat(),
                    "per_page": "100",
                    "page": str(page),
                },
            )
            if not isinstance(raw, list) or not raw:
                break
            for item in raw:
                if len(all_items) >= max_total_commits:
                    break
                if not isinstance(item, dict):
                    continue
                parsed = _commit_item_from_payload(repo, item)
                if parsed is None:
                    continue
                if wanted_authors and parsed.author.lower() not in wanted_authors:
                    continue
                if include_changed_files and detail_budget > 0:
                    try:
                        files = await _fetch_changed_files(
                            service=service,
                            owner=owner,
                            repo_name=repo_name,
                            sha=parsed.sha,
                        )
                    except ToolGatewayError:
                        files = ()
                    parsed = CommitItem(
                        repo=parsed.repo,
                        sha=parsed.sha,
                        author=parsed.author,
                        message=parsed.message,
                        committed_at=parsed.committed_at,
                        url=parsed.url,
                        files=files,
                    )
                    detail_budget -= 1
                all_items.append(parsed)
            if len(raw) < 100:
                break
            page += 1

    all_items.sort(key=lambda x: x.committed_at)
    return all_items


def _collect_commits(
    *,
    service: _GitHubRequester,
    repos: list[str],
    authors: list[str],
    since: datetime,
    until: datetime,
    include_changed_files: bool,
    max_detail_commits: int,
    max_total_commits: int,
) -> list[CommitItem]:
    return asyncio.run(
        _collect_commits_async(
            service=service,
            repos=repos,
            authors=authors,
            since=since,
            until=until,
            include_changed_files=include_changed_files,
            max_detail_commits=max_detail_commits,
            max_total_commits=max_total_commits,
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


def _metrics_file_path() -> Path:
    return state_dir() / "commit_digest_metrics.json"


def _record_metrics(
    *,
    date_label: str,
    success: bool,
    sample_size: int = 0,
    sample_correct: int = 0,
) -> None:
    path = _metrics_file_path()
    data: dict[str, dict[str, object]] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(key, str) and isinstance(value, dict):
                        data[key] = value
        except (OSError, ValueError):
            data = {}

    entry = data.get(date_label, {})
    total_runs = int(entry.get("total_runs", 0)) + 1
    success_runs = int(entry.get("success_runs", 0)) + (1 if success else 0)
    if sample_size <= 0:
        sample_size = int(entry.get("sample_size", 0))
    if sample_correct <= 0:
        sample_correct = int(entry.get("sample_correct", 0))
    accuracy = round((sample_correct / sample_size), 4) if sample_size > 0 else 0.0
    data[date_label] = {
        "date": date_label,
        "total_runs": total_runs,
        "success_runs": success_runs,
        "sample_size": sample_size,
        "sample_correct": sample_correct,
        "accuracy": accuracy,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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
    include_categories = commit_digest_include_categories()
    include_risk = commit_digest_include_risk()
    risk_paths = commit_digest_risk_paths() if include_risk else []
    exclude_types = commit_digest_exclude_types()
    max_detail_commits = commit_digest_max_classify_commits()
    max_total_commits = commit_digest_max_report_commits()
    include_changed_files = include_categories or include_risk

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
            include_changed_files=include_changed_files,
            max_detail_commits=max_detail_commits,
            max_total_commits=max_total_commits,
        )
        analytics = (
            _analyze_commits(commits=commits, exclude_types=exclude_types, risk_paths=risk_paths)
            if include_categories or include_risk
            else None
        )

        chunks = build_markdown_chunks(
            date_label=window.date_label,
            timezone=window.timezone,
            commits=commits,
            analytics=analytics,
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
        if analytics is not None:
            summary = build_summary_text(
                date_label=window.date_label,
                timezone=window.timezone,
                commits=commits,
                analytics=analytics,
            )
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
        _record_metrics(date_label=window.date_label, success=True)
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
        _record_metrics(date_label=window.date_label, success=False)
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
