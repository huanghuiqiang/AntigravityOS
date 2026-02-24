from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommitItem:
    repo: str
    sha: str
    author: str
    message: str
    committed_at: datetime
    url: str


def build_summary_text(*, date_label: str, timezone: str, commits: list[CommitItem]) -> str:
    repos = sorted({item.repo for item in commits})
    lines = [
        f"【Commit日报】每日 Commit 日报（{date_label}）",
        f"时区：{timezone}",
        f"总提交数：{len(commits)}",
        f"仓库数：{len(repos)}",
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


def build_markdown_chunks(
    *,
    date_label: str,
    timezone: str,
    commits: list[CommitItem],
    max_chars: int = 2000,
) -> list[str]:
    by_repo: dict[str, list[CommitItem]] = {}
    for item in commits:
        by_repo.setdefault(item.repo, []).append(item)

    chunks: list[str] = []
    base_header = [
        f"【Commit日报】每日 Commit 日报（{date_label}）",
        f"- 时区：{timezone}",
        f"- 总提交数：{len(commits)}",
        f"- 仓库数：{len(by_repo)}",
        "",
    ]

    current = "\n".join(base_header)
    for repo in sorted(by_repo.keys()):
        block = "\n".join(_build_repo_lines(repo, by_repo[repo]))
        if len(current) + len(block) + 1 > max_chars and current.strip():
            chunks.append(current.strip() + "\n")
            current = "\n".join(base_header) + block
        else:
            current += block

    if current.strip():
        chunks.append(current.strip() + "\n")

    if not chunks:
        chunks = ["\n".join(base_header).strip() + "\n"]

    total = len(chunks)
    with_index: list[str] = []
    for idx, chunk in enumerate(chunks, 1):
        first_line, sep, tail = chunk.partition("\n")
        indexed = f"{first_line}[{idx}/{total}]"
        with_index.append(indexed + (sep + tail if sep else "\n"))
    return with_index


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
