from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class CommitItem:
    repo: str
    sha: str
    author: str
    message: str
    committed_at: datetime
    url: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommitDigestAnalytics:
    total_commits: int
    effective_commits: int
    category_counts: dict[str, int] = field(default_factory=dict)
    high_risk_changes: int = 0
    revert_count: int = 0
    conclusion: str = "暂无结论"


def _top_categories_text(category_counts: dict[str, int], top_n: int = 2) -> str:
    ranked = sorted(category_counts.items(), key=lambda x: (-x[1], x[0]))
    if not ranked:
        return "-"
    return " / ".join(f"{name}({count})" for name, count in ranked[:top_n])


def build_summary_text(
    *,
    date_label: str,
    timezone: str,
    commits: list[CommitItem],
    analytics: CommitDigestAnalytics | None = None,
) -> str:
    repos = sorted({item.repo for item in commits})
    if analytics is None:
        lines = [
            f"【Commit日报】每日 Commit 日报（{date_label}）",
            f"时区：{timezone}",
            f"总提交数：{len(commits)}",
            f"仓库数：{len(repos)}",
        ]
        return "\n".join(lines)

    lines = [
        f"【Commit日报】{date_label}",
        f"时区：{timezone}",
        f"总提交：{analytics.total_commits}（有效提交：{analytics.effective_commits}）",
        f"Top 类别：{_top_categories_text(analytics.category_counts)}",
        f"高风险路径变更：{analytics.high_risk_changes}",
        f"revert：{analytics.revert_count}",
        f"结论：{analytics.conclusion}",
    ]
    return "\n".join(lines)


def _build_repo_lines(repo: str, items: list[CommitItem]) -> list[str]:
    lines = [f"### {repo}"]
    sorted_items = sorted(items, key=lambda x: x.committed_at)
    for item in sorted_items:
        short_sha = item.sha[:7]
        msg = item.message.splitlines()[0].strip()
        ts = item.committed_at.strftime("%H:%M")
        lines.append(f"- `{short_sha}` {msg} · {item.author} · {ts} · [链接]({item.url})")
    lines.append("")
    return lines


def _append_line_with_split(
    *,
    chunks: list[str],
    current: str,
    line: str,
    header: str,
    max_chars: int,
) -> str:
    candidate = f"{current}{line}\n"
    if len(candidate) <= max_chars:
        return candidate
    if current.strip():
        chunks.append(current.strip() + "\n")
    retry = f"{header}{line}\n"
    if len(retry) <= max_chars:
        return retry
    chunks.append(retry[:max_chars].rstrip() + "\n")
    return header


def _render_category_lines(category_counts: dict[str, int], *, top_n: int | None = None) -> list[str]:
    lines = ["分类明细："]
    ranked = sorted(category_counts.items(), key=lambda x: (-x[1], x[0]))
    if top_n is not None:
        ranked = ranked[:top_n]
    if not ranked:
        lines.append("- (none)")
    for name, count in ranked:
        lines.append(f"- {name}: {count}")
    lines.append("")
    return lines


def _render_header_lines(
    *,
    date_label: str,
    timezone: str,
    commits: list[CommitItem],
    analytics: CommitDigestAnalytics | None,
    compact_level: int,
) -> list[str]:
    repo_count = len({item.repo for item in commits})
    if analytics is None:
        return [
            f"【Commit日报】每日 Commit 日报（{date_label}）",
            f"- 时区：{timezone}",
            f"- 总提交数：{len(commits)}",
            f"- 仓库数：{repo_count}",
            "",
        ]

    lines = [
        f"【Commit日报】{date_label}",
        f"- 时区：{timezone}",
        f"- 总提交：{analytics.total_commits}（有效提交：{analytics.effective_commits}）",
        f"- Top 类别：{_top_categories_text(analytics.category_counts)}",
    ]
    if compact_level <= 2:
        lines.extend(_render_category_lines(analytics.category_counts, top_n=None if compact_level == 0 else 3))
    if compact_level <= 1:
        lines.extend(
            [
                "风险提示：",
                f"- 高风险路径变更：{analytics.high_risk_changes}",
                f"- revert：{analytics.revert_count}",
                "",
            ]
        )
    if compact_level == 0:
        lines.extend([f"结论：{analytics.conclusion}", ""])
    elif compact_level == 1:
        conclusion = analytics.conclusion.split("，")[0].strip()
        lines.extend([f"结论：{conclusion}", ""])
    return lines


def _render_short_fallback(
    *,
    date_label: str,
    commits: list[CommitItem],
    analytics: CommitDigestAnalytics | None,
) -> str:
    if analytics is None:
        return f"【Commit日报】{date_label} 提交{len(commits)}"
    top = _top_categories_text(analytics.category_counts)
    return (
        f"【Commit日报】{date_label} 提交{analytics.total_commits}，"
        f"Top: {top}，风险{analytics.high_risk_changes}"
    )


def build_markdown_chunks(
    *,
    date_label: str,
    timezone: str,
    commits: list[CommitItem],
    analytics: CommitDigestAnalytics | None = None,
    max_chars: int = 2000,
) -> list[str]:
    by_repo: dict[str, list[CommitItem]] = {}
    for item in commits:
        by_repo.setdefault(item.repo, []).append(item)

    for compact_level in range(0, 4):
        header_lines = _render_header_lines(
            date_label=date_label,
            timezone=timezone,
            commits=commits,
            analytics=analytics,
            compact_level=compact_level,
        )
        chunks: list[str] = []
        header = "\n".join(header_lines)
        current = header

        for repo in sorted(by_repo.keys()):
            for line in _build_repo_lines(repo, by_repo[repo]):
                current = _append_line_with_split(
                    chunks=chunks,
                    current=current,
                    line=line,
                    header=header,
                    max_chars=max_chars,
                )

        if current.strip():
            chunks.append(current.strip() + "\n")
        if not chunks:
            chunks = ["\n".join(header_lines).strip() + "\n"]

        too_long = any(len(chunk) > max_chars for chunk in chunks)
        if not too_long:
            total = len(chunks)
            with_index: list[str] = []
            for idx, chunk in enumerate(chunks, 1):
                first_line, sep, tail = chunk.partition("\n")
                indexed = f"{first_line}[{idx}/{total}]"
                with_index.append(indexed + (sep + tail if sep else "\n"))
            return with_index

    fallback = _render_short_fallback(date_label=date_label, commits=commits, analytics=analytics)
    return [f"{fallback}[1/1]\n"]


def build_feishu_post_payload(title: str, markdown: str) -> dict[str, object]:
    lines = [line for line in markdown.splitlines() if line.strip()]
    content: list[list[dict[str, str]]] = []
    for line in lines:
        content.append([{"tag": "text", "text": f"{line}\n"}])
    return {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content,
                }
            }
        },
    }


def build_feishu_text_payload(text: str) -> dict[str, object]:
    return {
        "msg_type": "text",
        "content": {
            "text": text,
        },
    }
