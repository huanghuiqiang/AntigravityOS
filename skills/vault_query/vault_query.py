"""
vault_query.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Vault Query CLI（供 OpenClaw Pi 调用）

Pi 在 Telegram 对话中调用此脚本，实现对 Obsidian Vault 的自然语言问答。

用法（Pi 调用时）：
  python3 vault_query.py search "Agent 架构"
  python3 vault_query.py get "Axiom - 工具是 Agent 的感官与手脚"
  python3 vault_query.py pending          # 列出待处理高分文章
  python3 vault_query.py axioms           # 列出所有 Axiom 标题
  python3 vault_query.py stats            # Inbox 统计快照
  python3 vault_query.py recent [N]       # 最近 N 条入库笔记（默认 5）
"""

import re
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from agos.config import vault_path, inbox_folder
from agos.frontmatter import parse_frontmatter as _parse_frontmatter

# ── Vault 配置 ────────────────────────────────────────────────────
VAULT = vault_path()
INBOX = VAULT / inbox_folder()
MAX_RESULTS     = 8     # 搜索最多返回的文件数
SNIPPET_CHARS   = 300   # 每个结果显示多少字符的正文摘要
MAX_NOTE_CHARS  = 4000  # get 命令返回的最大正文字符数


def _all_md_files(base: Path = VAULT) -> list[Path]:
    """递归列出 Vault 中所有 .md 文件（排除 .obsidian 等隐藏目录）。"""
    results = []
    for f in base.rglob("*.md"):
        if any(part.startswith(".") for part in f.parts):
            continue
        results.append(f)
    return results


def _rel(path: Path) -> str:
    """返回相对于 Vault 的路径字符串。"""
    try:
        return str(path.relative_to(VAULT))
    except ValueError:
        return str(path)


# ── 命令：search ─────────────────────────────────────────────────

def cmd_search(query: str) -> str:
    """
    在 Vault 全文（文件名 + 正文）搜索 query，返回最相关的 N 条。
    简单关键词匹配，按命中次数排序。
    """
    query_lower = query.lower()
    keywords    = query_lower.split()

    scored = []
    for f in _all_md_files():
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            name    = f.stem.lower()
            c_lower = content.lower()

            # 计分：文件名命中权重 3，正文命中权重 1
            score = sum(name.count(kw) * 3 + c_lower.count(kw) for kw in keywords)
            if score > 0:
                scored.append((score, f, content))
        except Exception:
            pass

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:MAX_RESULTS]

    if not top:
        return f'🔍 未找到包含 "{query}" 的笔记。'

    lines = [f'🔍 搜索 "{query}" — 找到 {len(top)} 条相关笔记：\n']
    for i, (score, f, content) in enumerate(top, 1):
        fm, body    = _parse_frontmatter(content)
        title       = fm.get("title", f.stem)
        tags        = fm.get("tags", [])
        status      = fm.get("status", "")
        note_score  = fm.get("score", "")

        # 提取关键词附近的正文片段
        snippet = ""
        for kw in keywords:
            idx = body.lower().find(kw)
            if idx != -1:
                start   = max(0, idx - 60)
                end     = min(len(body), idx + 140)
                snippet = "..." + body[start:end].replace("\n", " ").strip() + "..."
                break

        tag_str    = f" [{','.join(str(t) for t in tags[:3])}]" if tags else ""
        status_str = f" · {status}" if status else ""
        score_str  = f" · ⭐{note_score}" if note_score else ""
        rel        = _rel(f)

        lines.append(f"{i}. **{title}**{tag_str}{status_str}{score_str}")
        lines.append(f"   📄 `{rel}`")
        if snippet:
            lines.append(f"   💬 {snippet[:SNIPPET_CHARS]}")
        lines.append("")

    return "\n".join(lines)


# ── 命令：get ────────────────────────────────────────────────────

def cmd_get(name: str) -> str:
    """
    读取指定笔记的全文（fuzzy 文件名匹配）。
    name 可以是：文件名（不含扩展名）、精确路径、或模糊匹配词
    """
    name_lower = name.lower().strip()

    # 1. 精确路径
    exact = VAULT / (name if name.endswith(".md") else name + ".md")
    if exact.exists():
        return _fmt_note(exact)

    # 2. 文件名模糊匹配（优先选包含所有关键词的）
    candidates = []
    for f in _all_md_files():
        if name_lower in f.stem.lower():
            candidates.append(f)

    if not candidates:
        return f'📄 未找到笔记 "{name}"。\n提示：可以先用 `search` 命令找到文件名，再用 `get` 获取全文。'

    if len(candidates) == 1:
        return _fmt_note(candidates[0])

    # 多个候选：优先选文件名最短的（最精确的）
    best = sorted(candidates, key=lambda f: len(f.stem))[0]
    others = [f'  - `{_rel(f)}`' for f in candidates[1:4]]
    note_content = _fmt_note(best)
    if others:
        note_content += f"\n\n💡 还有其他匹配笔记：\n" + "\n".join(others)
    return note_content


def _fmt_note(f: Path) -> str:
    """格式化单条笔记内容供 Pi 阅读。"""
    try:
        content = f.read_text(encoding="utf-8", errors="ignore")
        fm, body = _parse_frontmatter(content)

        title  = fm.get("title", f.stem)
        tags   = fm.get("tags", [])
        status = fm.get("status", "")
        score  = fm.get("score", "")
        source = fm.get("source", "")
        date   = fm.get("created", "")

        header_parts = [f"📄 **{title}**"]
        if tags:   header_parts.append(f"[{', '.join(str(t) for t in tags[:4])}]")
        if score:  header_parts.append(f"⭐{score}")
        if status: header_parts.append(f"· {status}")
        if date:   header_parts.append(f"· {date}")

        lines = [" ".join(header_parts), f"📁 `{_rel(f)}`"]
        if source:
            lines.append(f"🔗 {source}")
        lines.append("")
        lines.append(body[:MAX_NOTE_CHARS])
        if len(body) > MAX_NOTE_CHARS:
            lines.append(f"\n... [内容已截断，原文 {len(body)} 字符]")
        return "\n".join(lines)
    except Exception as e:
        return f"读取笔记失败: {e}"


# ── 命令：pending ────────────────────────────────────────────────

def cmd_pending(limit: int = 10) -> str:
    """列出 Inbox 中 status: pending 的高分笔记，按分数倒序。"""
    items = []
    for f in _all_md_files(INBOX):
        try:
            fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
            if fm.get("status") == "pending":
                items.append({
                    "title":  fm.get("title", f.stem),
                    "score":  float(fm.get("score", 0)),
                    "source": fm.get("source", ""),
                    "date":   str(fm.get("created", "")),
                    "tags":   fm.get("tags", []),
                })
        except Exception:
            pass

    items.sort(key=lambda x: x["score"], reverse=True)
    top = items[:limit]

    if not top:
        return "✅ 当前没有 pending 条目，Inbox 已清空！"

    lines = [f"⏳ **Pending 队列** — 共 {len(items)} 条，显示 Top {len(top)}：\n"]
    for i, item in enumerate(top, 1):
        from urllib.parse import urlparse
        medal = "💎" if item["score"] >= 9.5 else "🥇" if item["score"] >= 8.5 else "⭐"
        host  = urlparse(item["source"]).netloc[:25] if item["source"] else "─"
        lines.append(f'{i}. {medal} [{item["score"]:.1f}] **{item["title"][:50]}**')
        lines.append(f'   {host} · {item["date"][:10]}')
        lines.append("")

    return "\n".join(lines)


# ── 命令：axioms ─────────────────────────────────────────────────

def cmd_axioms() -> str:
    """列出 Vault 中所有 Axiom 笔记的标题和核心内容。"""
    axiom_files = [f for f in _all_md_files() if f.stem.startswith("Axiom -")]
    axiom_files.sort(key=lambda f: f.stem)

    if not axiom_files:
        return "📚 Vault 中暂无 Axiom 笔记。"

    lines = [f"🧠 **所有 Axiom 笔记** — 共 {len(axiom_files)} 条：\n"]
    for f in axiom_files:
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            fm, body = _parse_frontmatter(content)
            # 提取 callout 摘要
            m = re.search(r">\s*\[!abstract\][^\n]*\n>\s*(.+?)(?:\n|$)", body)
            summary = m.group(1).strip() if m else ""
            name = f.stem.replace("Axiom - ", "")
            lines.append(f"✨ **{name}**")
            if summary:
                lines.append(f"   → {summary[:120]}")
        except Exception:
            lines.append(f"✨ {f.stem}")
        lines.append("")

    return "\n".join(lines)


# ── 命令：stats ──────────────────────────────────────────────────

def cmd_stats() -> str:
    """Inbox 状态快照。"""
    from collections import Counter
    all_notes = []
    for f in _all_md_files(INBOX):
        try:
            fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
            tags  = fm.get("tags", [])
            if isinstance(tags, str): tags = [tags]
            if any(t in tags for t in ["BouncerDump", "WebClip", "PDFIngested"]):
                all_notes.append(fm)
        except Exception:
            pass

    total   = len(all_notes)
    counter = Counter(n.get("status", "unknown") for n in all_notes)
    today   = datetime.now().strftime("%Y-%m-%d")

    today_count = sum(1 for n in all_notes if str(n.get("created", "")).startswith(today))

    lines = [
        "📊 **Vault Inbox 快照**\n",
        f"📥 总入库：**{total}** 条",
        f"⏳ Pending：**{counter.get('pending', 0)}** 条",
        f"✅ Done：**{counter.get('done', 0)}** 条",
        f"❌ Error：**{counter.get('error', 0)}** 条",
        f"📅 今日新增：**{today_count}** 条",
        "",
        f"🗓 统计时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return "\n".join(lines)


# ── 命令：recent ─────────────────────────────────────────────────

def cmd_recent(n: int = 5) -> str:
    """最近 N 条入库笔记（按 created 倒序）。"""
    items = []
    for f in _all_md_files(INBOX):
        try:
            fm, _ = _parse_frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
            tags  = fm.get("tags", [])
            if isinstance(tags, str): tags = [tags]
            if not any(t in tags for t in ["BouncerDump", "WebClip", "PDFIngested"]):
                continue
            items.append({
                "title":   fm.get("title", f.stem),
                "score":   float(fm.get("score", 0)),
                "created": str(fm.get("created", "")),
                "status":  fm.get("status", ""),
                "source":  fm.get("source", ""),
                "is_clip": "WebClip" in tags,
            })
        except Exception:
            pass

    items.sort(key=lambda x: x["created"], reverse=True)
    top = items[:n]

    if not top:
        return "📭 Inbox 中暂无笔记。"

    lines = [f"🕐 **最近 {len(top)} 条入库笔记：**\n"]
    for i, item in enumerate(top, 1):
        medal  = "💎" if item["score"] >= 9.5 else "🥇" if item["score"] >= 8.5 else "⭐"
        kind   = "✂️ Clip" if item["is_clip"] else "🤖 RSS"
        status = item["status"] or "─"
        lines.append(
            f'{i}. {medal} [{item["score"]:.1f}] **{item["title"][:45]}**\n'
            f'   {kind} · {item["created"][:10]} · {status}'
        )
        lines.append("")

    return "\n".join(lines)


# ── CLI 入口 ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Vault Query CLI — 供 OpenClaw Pi 调用",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # search
    p_search = sub.add_parser("search", help="全文搜索 Vault")
    p_search.add_argument("query", help="搜索关键词（支持多词）")

    # get
    p_get = sub.add_parser("get", help="读取特定笔记全文")
    p_get.add_argument("name", help="笔记名称（模糊匹配）")

    # pending
    p_pending = sub.add_parser("pending", help="列出 pending 高分文章")
    p_pending.add_argument("--limit", type=int, default=10)

    # axioms
    sub.add_parser("axioms", help="列出所有 Axiom 笔记")

    # stats
    sub.add_parser("stats", help="Inbox 统计快照")

    # recent
    p_recent = sub.add_parser("recent", help="最近入库笔记")
    p_recent.add_argument("n", type=int, nargs="?", default=5, help="显示条数（默认5）")

    args = parser.parse_args()

    if args.cmd == "search":
        print(cmd_search(args.query))
    elif args.cmd == "get":
        print(cmd_get(args.name))
    elif args.cmd == "pending":
        print(cmd_pending(args.limit))
    elif args.cmd == "axioms":
        print(cmd_axioms())
    elif args.cmd == "stats":
        print(cmd_stats())
    elif args.cmd == "recent":
        print(cmd_recent(args.n))


if __name__ == "__main__":
    main()
