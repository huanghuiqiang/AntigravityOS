"""
synthesizer.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Axiom Synthesizer Agent

职责：
  1. 扫描 Obsidian Inbox，收集所有已有 axiom_extracted 的笔记
  2. 将碎片公理提交给 LLM，做：去重 → 分类 → 命名 → 排序
  3. 生成新的 Axiom 候选条目
  4. 更新 `000 认知架构地图.md`
  5. 可选：为每条新 Axiom 创建独立笔记文件
  6. Telegram 推送合成结果摘要

触发方式：
  - 手动：python -m agents.axiom_synthesizer.synthesizer
  - 建议频率：每周一次（周日晚）

注意：
  - 本脚本是**只追加**的——不会删除或修改地图已有条目
  - 已存在于地图中的 Axiom 标题会被自动跳过（幂等）
"""

import re
import json
import argparse
import httpx
from pathlib import Path
from datetime import datetime

from agos.config import (
    openrouter_api_key, vault_path, inbox_folder,
    min_score_threshold, model_synthesizer, synth_max_batch,
)
from agos.notify import send_message
from agos.frontmatter import parse_frontmatter

from skills.obsidian_bridge.bridge import (
    get_vault, list_notes, read_note, write_note, append_note,
    update_frontmatter,
)

# ── 配置 ─────────────────────────────────────────────────────────
MAP_FILE = "000 认知架构地图.md"
INBOX_FOLDER = inbox_folder()
MIN_AXIOM_SCORE = min_score_threshold()
MAX_AXIOMS_BATCH = synth_max_batch()


# ── Step 1: 收集碎片公理 ─────────────────────────────────────────
def _warn(scope: str, detail: str, err: Exception | None = None):
    if err is None:
        print(f"  ⚠️ [{scope}] {detail}")
    else:
        print(f"  ⚠️ [{scope}] {detail}: {err}")



def collect_raw_axioms() -> list[dict]:
    """
    扫描 Inbox 中所有 BouncerDump / WebClip 笔记，
    提取 [!abstract] callout 中的公理文本。
    跳过已打标 synthesized: true 的笔记。
    """
    vault = get_vault()
    inbox_dir = vault / INBOX_FOLDER
    raw = []
    seen_axioms: set[str] = set()

    def _try_extract(f: Path):
        try:
            content = f.read_text(encoding="utf-8")
            fm, body = parse_frontmatter(content)

            # 增量逻辑：跳过已合成笔记
            if fm.get("synthesized") is True:
                return

            tags = fm.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]
            if not any(t in tags for t in ["BouncerDump", "WebClip", "PDFIngested"]):
                return
            score = float(fm.get("score", 0))
            if score < MIN_AXIOM_SCORE:
                return

            # 匹配实际格式
            axiom = ""
            m = re.search(
                r">\s*\[!abstract\][^\n]*\n>\s*(.+?)(?:\n|$)",
                body
            )
            if m:
                axiom = m.group(1).strip()

            if not axiom:
                m2 = re.search(r"\[!abstract\].*?\n>\s*(.+?)(?:\n|$)", content)
                if m2:
                    axiom = m2.group(1).strip()

            if not axiom or axiom in ("待提炼", ""):
                return

            # 去重
            key = axiom[:80]
            if key in seen_axioms:
                return
            seen_axioms.add(key)

            raw.append({
                "axiom": axiom,
                "score": score,
                "source": str(fm.get("source", "")),
                "title": str(fm.get("title", f.stem)),
                "path": str(f)
            })
        except Exception as e:
            _warn("synthesizer/collect", f"解析笔记失败: {f}", e)

    def _scan_dir(d: Path):
        for f in d.iterdir():
            if f.is_dir():
                _scan_dir(f)
            elif f.suffix == ".md":
                _try_extract(f)

    if inbox_dir.exists():
        _scan_dir(inbox_dir)

    print(f"  📚 共收集到 {len(raw)} 条新公理碎片（score ≥ {MIN_AXIOM_SCORE}，增量扫描）")
    return raw


def mark_as_synthesized(paths: list[str]):
    """将已提取公理的笔记打上 synthesized: true 标记。"""
    print(f"  标记 {len(paths)} 条笔记为已合成...")
    for p in paths:
        update_frontmatter(p, {"synthesized": True})


# ── Step 2: 读取现有地图（防止重复追加）────────────────────────

def read_map() -> str:
    map_path = get_vault() / MAP_FILE
    if map_path.exists():
        return map_path.read_text(encoding="utf-8")
    return ""


def extract_existing_axiom_titles(map_content: str) -> set[str]:
    return set(re.findall(r"\[\[Axiom - ([^\]]+)\]\]", map_content))


# ── Step 3: LLM 合成 ─────────────────────────────────────────────

SYNTHESIS_PROMPT = """
你是 Antigravity OS 的"认知蒸馏师"。你的任务是对收集到的碎片公理做：

1. **语义去重**：合并表达相同底层规律的公理
2. **提升抽象层**：将过于具体的描述升华为可复用的"第一性原理"
3. **命名规范化**：每条公理采用格式 `公理名称 (副标题/关键词)`
4. **排序**：按"认知密度"从高到低排列

输出格式必须是合法的 JSON 数组，每个元素包含：
{{"name": "简洁的英文/中文公理名称 (关键词)", "meaning": "一句话：这条公理的底层规律是什么", "sources": ["来源标题1"], "is_new": true}}

重要约束：
- 只返回 JSON 数组，不要任何 Markdown 包裹
- 最多输出 8 条（优中选优）
- 如果碎片中没有任何值得提炼的新公理，返回空数组 []

以下是已存在于认知地图中的公理（请勿重复）：
{existing}

以下是本次收集到的碎片公理（JSON 格式）：
{raw_axioms}
"""


def synthesize_with_llm(raw_axioms: list[dict], existing_titles: set[str]) -> tuple[list[dict], list[str]]:
    api_key = openrouter_api_key()
    if not api_key:
        print("  ❌ 未找到 API Key")
        return [], []

    unique_axioms = []
    seen = set()
    for a in raw_axioms:
        key = a["axiom"][:60]
        if key not in seen:
            seen.add(key)
            unique_axioms.append(a)

    batch = unique_axioms[:MAX_AXIOMS_BATCH]
    processed_paths = [a["path"] for a in batch if "path" in a]

    model = model_synthesizer()
    print(f"  🧠 提交 {len(batch)} 条碎片给 {model} 合成...")

    llm_batch = [{"axiom": a["axiom"], "title": a["title"]} for a in batch]

    prompt = SYNTHESIS_PROMPT.format(
        existing="\n".join(f"- {t}" for t in sorted(existing_titles)) or "(无)",
        raw_axioms=json.dumps(llm_batch, ensure_ascii=False, indent=2),
    )

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/huanghuiqiang/AntigravityOS",
                    "X-Title": "Antigravity Axiom Synthesizer",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
            )

        if resp.status_code != 200:
            print(f"  ❌ LLM 响应异常: HTTP {resp.status_code}")
            return [], []

        raw_out = resp.json()["choices"][0]["message"]["content"]
        clean = raw_out.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list):
                    parsed = v
                    break
            else:
                parsed = []

        print(f"  ✅ 合成出 {len(parsed)} 条候选公理")
        return parsed, processed_paths

    except Exception as e:
        print(f"  ❌ LLM 合成出错: {e}")
        return [], []


# ── Step 4: 更新认知地图 ─────────────────────────────────────────

def update_map(synthesized: list[dict], dry_run: bool = False) -> list[str]:
    if not synthesized:
        return []

    map_path = get_vault() / MAP_FILE
    map_content = read_map()
    existing = extract_existing_axiom_titles(map_content)

    new_ones = [
        a for a in synthesized
        if a.get("is_new", True)
        and not any(
            a["name"].lower() in t.lower() or t.lower() in a["name"].lower()
            for t in existing
        )
    ]

    if not new_ones:
        print("  ℹ️  所有合成公理已存在于地图，无需追加")
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    num_start = len(re.findall(r"^\d+\.\s+\*\*", map_content, re.MULTILINE)) + 1
    new_lines = [
        f"\n\n---\n\n## 🆕 Synthesizer 追加 ({today})\n"
        f"> 由 Axiom Synthesizer 从 Bouncer 输出中自动提炼\n"
    ]

    written = []
    for i, axiom in enumerate(new_ones, num_start):
        name = axiom.get("name", "未命名公理")
        meaning = axiom.get("meaning", "")
        sources = axiom.get("sources", [])
        src_str = "、".join(sources[:3]) if sources else ""

        entry = (
            f"{i}. **{name}**: [[Axiom - {name}]]\n"
            f"    *   *Meaning*: {meaning}\n"
        )
        if src_str:
            entry += f"    *   *源自*: {src_str}\n"

        new_lines.append(entry)
        written.append(name)

    append_block = "\n".join(new_lines)

    if dry_run:
        print("\n[DRY RUN] 将追加以下内容到认知地图：")
        print(append_block)
        return written

    with map_path.open("a", encoding="utf-8") as f:
        f.write(append_block)

    print(f"  ✅ 已追加 {len(written)} 条新公理到认知地图")
    return written


# ── Step 5: 为每条新 Axiom 创建独立笔记 ──────────────────

def create_axiom_notes(synthesized: list[dict], dry_run: bool = False) -> list[str]:
    created = []
    for axiom in synthesized:
        name = axiom.get("name", "")
        meaning = axiom.get("meaning", "")
        sources = axiom.get("sources", [])
        if not name:
            continue

        safe_name = re.sub(r'[\\/*?:"<>|]', "", name)[:80].strip()
        filename = f"Axiom - {safe_name}.md"
        note_path = get_vault() / filename

        if note_path.exists():
            continue

        today = datetime.now().strftime("%Y-%m-%d")
        src_links = "\n".join(f"- {s}" for s in sources) if sources else "- (自动合成)"

        content = f"""---
tags:
  - Axiom
  - AutoSynthesized
created: "{today}"
---

# {name}

> [!abstract] 核心公理
> {meaning}

## 推导与背景

本条公理由 **Axiom Synthesizer** 从以下信息源中自动提炼：

{src_links}

## 与认知架构的关联

- [[000 认知架构地图]]

---
*由 AntigravityOS Axiom Synthesizer 自动生成 · {today}*
"""
        if not dry_run:
            note_path.write_text(content, encoding="utf-8")
            print(f"  📄 创建 Axiom 笔记: {filename}")
        else:
            print(f"  [DRY RUN] 将创建: {filename}")

        created.append(str(note_path))

    return created


# ── Step 6: Telegram 通知 ────────────────────────────────────────

def notify(written: list[str], created_notes: list[str], total_raw: int, dry_run: bool):
    if dry_run:
        return

    if not written:
        text = (
            "🧬 <b>Axiom Synthesizer 运行完毕</b>\n\n"
            f"📚 已分析 <b>{total_raw}</b> 条公理碎片\n"
            "ℹ️ 无新公理需要追加（均已存在于认知地图）"
        )
    else:
        lines = [
            "🧬 <b>Axiom Synthesizer — 新公理提炼完成</b>",
            f"📚 分析 <b>{total_raw}</b> 条碎片 → 提炼 <b>{len(written)}</b> 条新公理\n",
        ]
        for name in written:
            lines.append(f"✨ <b>{name}</b>")
        lines.append(f"\n📝 已追加到 [[000 认知架构地图]]")
        if created_notes:
            lines.append(f"📂 创建独立笔记 {len(created_notes)} 个")
        text = "\n".join(lines)

    send_message(text)


# ── 主流程 ────────────────────────────────────────────────────────

def main(dry_run: bool = False, create_notes: bool = True):
    print("=" * 55)
    print("🧬 [Axiom Synthesizer] 启动...")
    print(f"   Vault:    {get_vault()}")
    print(f"   地图:     {MAP_FILE}")
    print(f"   Dry Run:  {dry_run}")
    print("=" * 55)

    # 1. 采集碎片
    raw_axioms = collect_raw_axioms()
    if not raw_axioms:
        print("\n⚠️  未收集到有效公理碎片，退出。")
        return

    # 2. 读现有地图，防重复
    map_content = read_map()
    existing_titles = extract_existing_axiom_titles(map_content)
    print(f"  🗺️  认知地图已有 {len(existing_titles)} 条公理")

    # 3. LLM 合成
    synthesized, processed_paths = synthesize_with_llm(raw_axioms, existing_titles)
    if not synthesized:
        print("\n⚠️  LLM 未合成出新公理。")
        if not dry_run and processed_paths:
            mark_as_synthesized(processed_paths)
        notify([], [], len(raw_axioms), dry_run)
        return

    # 4. 更新地图
    written = update_map(synthesized, dry_run=dry_run)

    # 5. 创建独立笔记（可选）
    created_notes = []
    if create_notes and written:
        created_notes = create_axiom_notes(synthesized, dry_run=dry_run)

    # 6. 标记为已合成（增量关键）
    if not dry_run and processed_paths:
        mark_as_synthesized(processed_paths)

    # 7. 推送通知
    notify(written, created_notes, len(raw_axioms), dry_run)

    # 8. 汇总输出
    print("\n" + "=" * 55)
    print(f"✅ 合成完成")
    print(f"   原始碎片:  {len(raw_axioms)} 条")
    print(f"   新增公理:  {len(written)} 条")
    print(f"   独立笔记:  {len(created_notes)} 个")
    print("=" * 55)
    for name in written:
        print(f"   ✨ {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity Axiom Synthesizer")
    parser.add_argument("--dry-run", action="store_true", help="只分析，不写入")
    parser.add_argument("--no-notes", action="store_true", help="不创建独立 Axiom 笔记")
    parser.add_argument("--min-score", type=float, default=MIN_AXIOM_SCORE)
    parser.add_argument("--max-batch", type=int, default=MAX_AXIOMS_BATCH)
    args = parser.parse_args()

    MIN_AXIOM_SCORE = args.min_score
    MAX_AXIOMS_BATCH = args.max_batch

    main(dry_run=args.dry_run, create_notes=not args.no_notes)
