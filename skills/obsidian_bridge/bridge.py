"""
obsidian_bridge.py
──────────────────
Antigravity OS 的 Obsidian 读写工具。
提供对 Obsidian Vault 的 Python CRUD API。

核心能力：
  - read_note(path)         → 读取任意笔记内容
  - write_note(path, body)  → 覆盖写入笔记
  - append_note(path, text) → 追加内容
  - list_notes(folder)      → 列出指定文件夹的所有 .md 文件
  - scan_pending()          → 扫描 Inbox 中 status: pending 的笔记
  - update_frontmatter()    → 更新 YAML frontmatter 中的字段
  - create_axiom()          → 按标准格式创建 Axiom 正式笔记

默认 Vault：/Users/hugh/Documents/Obsidian/AINotes
通过环境变量 OBSIDIAN_VAULT 覆盖。
"""

import os
import re
import yaml
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── 配置 ──────────────────────────────────────────────────────────
DEFAULT_VAULT = "/Users/hugh/Documents/Obsidian/AINotes"
INBOX_FOLDER  = "00_Inbox"

def get_vault() -> Path:
    vault = os.getenv("OBSIDIAN_VAULT", DEFAULT_VAULT)
    return Path(vault)

def get_inbox() -> Path:
    return get_vault() / INBOX_FOLDER

# ── 内部工具 ──────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    拆分 YAML frontmatter 和正文。
    Returns: (frontmatter_dict, body_str)
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    yaml_str = content[3:end].strip()
    body     = content[end + 4:].lstrip("\n")

    try:
        fm = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        fm = {}

    return fm, body


def _build_content(frontmatter: dict, body: str) -> str:
    """把 frontmatter dict + body 重新组合成完整笔记字符串。"""
    if not frontmatter:
        return body
    fm_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).rstrip()
    return f"---\n{fm_str}\n---\n\n{body}"


def _resolve_path(path: str) -> Path:
    """
    路径解析：
      - 绝对路径 → 直接使用
      - 相对路径 → 相对于 Vault 根目录
      - 仅文件名 → 在 00_Inbox 中查找
    """
    p = Path(path)
    if p.is_absolute():
        return p
    # 如果 path 以 00_Inbox 或其他文件夹开头，直接拼 vault
    full = get_vault() / p
    if full.exists():
        return full
    # 降级到 Inbox
    return get_inbox() / p

# ── 公开 API ──────────────────────────────────────────────────────

def read_note(path: str) -> Optional[str]:
    """读取笔记全文。返回 None 表示文件不存在。"""
    p = _resolve_path(path)
    if not p.exists():
        print(f"  [obsidian_bridge] 文件不存在: {p}")
        return None
    return p.read_text(encoding="utf-8")


def write_note(path: str, content: str, overwrite: bool = True) -> bool:
    """写入笔记（默认覆盖）。path 不存在会自动创建父目录。"""
    p = _resolve_path(path)
    if p.exists() and not overwrite:
        print(f"  [obsidian_bridge] 文件已存在，跳过: {p}")
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"  ✅ [obsidian_bridge] 写入: {p.name}")
    return True


def append_note(path: str, text: str) -> bool:
    """在笔记末尾追加内容（自动换行）。"""
    p = _resolve_path(path)
    if not p.exists():
        print(f"  [obsidian_bridge] 文件不存在，无法追加: {p}")
        return False
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\n{text}")
    print(f"  ✅ [obsidian_bridge] 追加: {p.name}")
    return True


def list_notes(folder: str = INBOX_FOLDER, pattern: str = "*.md") -> list[Path]:
    """列出指定文件夹下的所有 Markdown 笔记。"""
    base = get_vault() / folder
    if not base.exists():
        print(f"  [obsidian_bridge] 文件夹不存在: {base}")
        return []
    found = sorted(base.glob(pattern))
    return [f for f in found if f.is_file()]


def get_frontmatter(path: str) -> dict:
    """仅读取并返回 frontmatter dict。"""
    content = read_note(path)
    if content is None:
        return {}
    fm, _ = _parse_frontmatter(content)
    return fm


def update_frontmatter(path: str, updates: dict) -> bool:
    """
    更新笔记的 YAML frontmatter（仅修改指定字段，不动正文）。
    
    示例：
        update_frontmatter("00_Inbox/Bouncer - xxx.md", {"status": "done"})
    """
    content = read_note(path)
    if content is None:
        return False

    fm, body = _parse_frontmatter(content)
    fm.update(updates)
    new_content = _build_content(fm, body)

    p = _resolve_path(path)
    p.write_text(new_content, encoding="utf-8")
    print(f"  ✅ [obsidian_bridge] frontmatter 已更新: {p.name} → {updates}")
    return True


def scan_pending(min_score: float = 8.0) -> list[dict]:
    """
    扫描 00_Inbox 中所有 status: pending 且 score >= min_score 的笔记。
    
    Returns: list of {path, title, score, source, tags}
    """
    results = []
    for note_path in list_notes(INBOX_FOLDER):
        content = note_path.read_text(encoding="utf-8")
        fm, _ = _parse_frontmatter(content)

        status = fm.get("status", "")
        score  = float(fm.get("score", 0))

        if status == "pending" and score >= min_score:
            results.append({
                "path":   str(note_path),
                "title":  fm.get("title", note_path.stem),
                "score":  score,
                "source": fm.get("source", ""),
                "tags":   fm.get("tags", []),
                "fm":     fm,
            })

    print(f"  📥 [obsidian_bridge] 扫描完成：{len(results)} 条 pending 待处理")
    return results


def create_axiom(
    title: str,
    core_principle: str,
    reasoning: str,
    source_url: str = "",
    tags: list[str] = None,
) -> str:
    """
    在 Vault 根目录创建一条标准格式的 Axiom 笔记。
    
    Returns: 创建的文件路径（str）
    """
    if tags is None:
        tags = ["Axiom"]

    # 文件名：Axiom - {title}.md
    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:80].strip()
    filename   = f"Axiom - {safe_title}.md"
    target     = get_vault() / filename

    today = datetime.now().strftime("%Y-%m-%d")

    frontmatter = {
        "tags":    tags,
        "created": today,
        "source":  source_url,
    }
    body = f"""# {title}

> [!abstract] 核心公理
> {core_principle}

## 推导与背景

{reasoning}

## 与认知架构的关联

- [[000 认知架构地图]]
"""
    content = _build_content(frontmatter, body)
    write_note(str(target), content)
    return str(target)


def move_to_dated_folder(path: str, base_folder: str = INBOX_FOLDER) -> Optional[str]:
    """
    将 Inbox 中的文件移动到按日期归档的子文件夹。
    例如：00_Inbox/note.md → 00_Inbox/2026-02-21/note.md
    """
    src = _resolve_path(path)
    if not src.exists():
        return None

    today  = datetime.now().strftime("%Y-%m-%d")
    dst_dir = get_vault() / base_folder / today
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name

    src.rename(dst)
    print(f"  📁 [obsidian_bridge] 归档: {src.name} → {today}/")
    return str(dst)


# ── CLI 快速测试 ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== obsidian_bridge 自检 ===")
    print(f"Vault: {get_vault()}")
    print(f"Inbox: {get_inbox()}")

    notes = list_notes()
    print(f"Inbox 中共 {len(notes)} 条笔记")

    pending = scan_pending()
    print(f"待处理 (status=pending): {len(pending)} 条")
    for p in pending:
        print(f"  [{p['score']}] {p['title']}")
