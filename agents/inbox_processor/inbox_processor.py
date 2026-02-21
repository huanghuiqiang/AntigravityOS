"""
inbox_processor.py
──────────────────
Antigravity OS | Inbox 消费者 Agent

职责：
  1. 扫描 Obsidian 00_Inbox 中 status=pending 且 score >= 8.0 的笔记
  2. 对每篇文章调用 NotebookLM 生成深度 Report（study-guide 格式）
  3. 将 NotebookLM 报告追加到原笔记
  4. 更新 frontmatter: status → done
  5. 将处理完的笔记归档到日期文件夹
  6. 推送 Telegram 通知（处理完成摘要）

触发方式：
  - cron 定时：每天 10:30，在 bouncer 跑完后执行
  - 手动：python inbox_processor.py [--dry-run]

依赖：
  - skills/obsidian_bridge/bridge.py（Obsidian 读写）
  - notebooklm CLI（需已登录：notebooklm login）
  - sys.path 需包含 Antigravity 根目录（由 init_env.sh 处理）
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── 路径初始化 ────────────────────────────────────────────────────
# 允许从任意目录执行本脚本
_THIS_DIR = Path(__file__).parent
_ROOT     = _THIS_DIR.parent.parent   # Antigravity OS 根目录
sys.path.insert(0, str(_ROOT))

load_dotenv(_THIS_DIR / ".env")
load_dotenv(_THIS_DIR.parent.parent / "agents/cognitive_bouncer/.env")  # 共用 Telegram 配置

# ── 导入内部模块 ──────────────────────────────────────────────────
from skills.obsidian_bridge.bridge import (
    scan_pending,
    update_frontmatter,
    append_note,
    move_to_dated_folder,
    get_vault,
)

# 复用 bouncer 的 Telegram 模块
_BOUNCER = _ROOT / "agents/cognitive_bouncer"
sys.path.insert(0, str(_BOUNCER))
from telegram_notify import send_message

# ── 配置 ──────────────────────────────────────────────────────────
MIN_SCORE     = float(os.getenv("INBOX_MIN_SCORE", "8.0"))
NLM_TIMEOUT   = int(os.getenv("NLM_TIMEOUT", "900"))      # 15 分钟
ARCHIVE_DONE  = os.getenv("INBOX_ARCHIVE_DONE", "true").lower() == "true"

# ── NotebookLM 集成 ───────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """运行子命令，返回 (returncode, stdout, stderr)。"""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def process_with_notebooklm(title: str, source_url: str, note_path: str) -> dict:
    """
    对单篇文章：
      1. 创建 NotebookLM notebook
      2. 添加 source（URL）
      3. 等待 source 处理完毕
      4. 生成 study-guide 报告
      5. 等待生成完成
      6. 下载报告内容
    
    Returns: {"success": bool, "notebook_id": str, "report": str, "error": str}
    """
    result = {"success": False, "notebook_id": "", "report": "", "error": ""}

    # Step 1: 创建 notebook
    safe_name = title[:50].replace('"', "'")
    rc, out, err = _run(["notebooklm", "create", f"Bouncer: {safe_name}", "--json"], timeout=30)
    if rc != 0:
        result["error"] = f"创建 notebook 失败: {err}"
        return result

    try:
        nb_data = json.loads(out)
        notebook_id = nb_data["id"]
        result["notebook_id"] = notebook_id
        print(f"    📓 Notebook 创建成功: {notebook_id[:8]}...")
    except (json.JSONDecodeError, KeyError) as e:
        result["error"] = f"解析 notebook ID 失败: {e} | 原始输出: {out}"
        return result

    # Step 2: 添加 source（优先用 URL，无 URL 则跳过）
    if source_url:
        rc, out, err = _run(
            ["notebooklm", "source", "add", source_url, "--notebook", notebook_id, "--json"],
            timeout=30
        )
        if rc != 0:
            print(f"    ⚠️  添加 source 失败（继续）: {err[:100]}")
        else:
            try:
                src_data = json.loads(out)
                source_id = src_data.get("source_id", "")
                print(f"    🔗 Source 添加中: {source_id[:8]}...")

                # Step 3: 等待 source 处理
                if source_id:
                    rc2, _, _ = _run(
                        ["notebooklm", "source", "wait", source_id,
                         "--notebook", notebook_id, "--timeout", "120"],
                        timeout=130
                    )
                    if rc2 == 0:
                        print(f"    ✅ Source 处理完毕")
                    else:
                        print(f"    ⚠️  Source 处理超时，继续生成...")
            except (json.JSONDecodeError, KeyError):
                pass
    else:
        print(f"    ⚠️  无源 URL，直接生成报告...")

    # Step 4: 生成 study-guide 报告
    rc, out, err = _run(
        ["notebooklm", "generate", "report",
         "--format", "study-guide",
         "--notebook", notebook_id,
         "--json"],
        timeout=60
    )
    if rc != 0:
        result["error"] = f"生成报告失败: {err}"
        return result

    try:
        gen_data  = json.loads(out)
        task_id   = gen_data.get("task_id", "")
        print(f"    🔄 报告生成中，task_id: {task_id[:8]}...")
    except (json.JSONDecodeError, KeyError) as e:
        result["error"] = f"解析 task_id 失败: {e}"
        return result

    # Step 5: 等待报告完成
    rc, out, err = _run(
        ["notebooklm", "artifact", "wait", task_id,
         "--notebook", notebook_id,
         "--timeout", str(NLM_TIMEOUT)],
        timeout=NLM_TIMEOUT + 30
    )
    if rc == 2:
        result["error"] = f"报告生成超时（>{NLM_TIMEOUT}s）"
        return result
    if rc != 0:
        result["error"] = f"等待报告失败: {err}"
        return result

    # Step 6: 下载报告内容
    tmp_path = f"/tmp/nlm_report_{notebook_id[:8]}.md"
    rc, out, err = _run(
        ["notebooklm", "download", "report", tmp_path,
         "--notebook", notebook_id],
        timeout=30
    )
    if rc != 0:
        result["error"] = f"下载报告失败: {err}"
        return result

    try:
        report_content = Path(tmp_path).read_text(encoding="utf-8")
        result["success"] = True
        result["report"]  = report_content
        print(f"    📄 报告下载成功（{len(report_content)} 字符）")
    except FileNotFoundError:
        result["error"] = "报告文件未找到"

    return result

# ── 主流水线 ──────────────────────────────────────────────────────

def process_note(note: dict, dry_run: bool = False) -> dict:
    """处理单个 pending 笔记，返回结果 dict。"""
    path      = note["path"]
    title     = note["title"]
    score     = note["score"]
    source    = note["source"]
    note_name = Path(path).name

    print(f"\n  🔍 处理: [{score}分] {title[:60]}")

    outcome = {
        "title":   title,
        "score":   score,
        "success": False,
        "notebook_id": "",
        "error":   "",
    }

    if dry_run:
        print(f"    [DRY RUN] 跳过实际处理")
        outcome["success"] = True
        return outcome

    # 调用 NotebookLM
    nlm_result = process_with_notebooklm(title, source, path)
    outcome["notebook_id"] = nlm_result.get("notebook_id", "")

    if nlm_result["success"]:
        # 追加报告到笔记
        report_section = f"""
---

## 🤖 NotebookLM 深度报告

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}
> Notebook ID：`{nlm_result['notebook_id']}`

{nlm_result['report']}
"""
        append_note(note_name, report_section)

        # 更新 frontmatter: pending → done
        update_frontmatter(note_name, {
            "status":        "done",
            "processed_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "notebook_id":   nlm_result["notebook_id"],
        })

        # 归档到日期文件夹
        if ARCHIVE_DONE:
            move_to_dated_folder(note_name)

        outcome["success"] = True
        print(f"    ✅ 处理完成并归档")
    else:
        # 标记为 error，不阻塞后续
        update_frontmatter(note_name, {
            "status": "error",
            "error":  nlm_result["error"][:200],
        })
        outcome["error"] = nlm_result["error"]
        print(f"    ❌ 处理失败: {nlm_result['error'][:80]}")

    return outcome


def build_telegram_report(results: list[dict], total_pending: int) -> str:
    """构建 Telegram 推送文本。"""
    success_list = [r for r in results if r["success"]]
    fail_list    = [r for r in results if not r["success"]]

    lines = [
        "🧠 <b>Inbox Processor 报告</b>",
        f"📊 发现 <b>{total_pending}</b> 条 pending → 处理 <b>{len(results)}</b> 条",
        f"✅ 成功 <b>{len(success_list)}</b> 条 | ❌ 失败 <b>{len(fail_list)}</b> 条",
        "",
    ]

    for r in success_list:
        lines.append(f"💎 [{r['score']:.1f}分] {r['title'][:50]}")
        if r.get("notebook_id"):
            lines.append(f"   📓 <code>{r['notebook_id'][:12]}...</code>")

    if fail_list:
        lines.append("\n⚠️ 失败条目：")
        for r in fail_list:
            lines.append(f"  ❌ {r['title'][:40]} → {r['error'][:60]}")

    return "\n".join(lines)


def main(dry_run: bool = False, limit: int = 0):
    print("=" * 55)
    print("🚀 [Inbox Processor] 启动...")
    print(f"   Vault: {get_vault()}")
    print(f"   最低分数门槛: {MIN_SCORE}")
    print(f"   Dry Run: {dry_run}")
    print("=" * 55)

    # 1. 扫描所有 pending 笔记
    pending = scan_pending(min_score=MIN_SCORE)
    total_pending = len(pending)

    if not pending:
        print("\n✅ 无 pending 条目，退出。")
        return

    # 支持限制本次最大处理数（防止一次性消耗太多 API）
    if limit > 0:
        pending = pending[:limit]
        print(f"\n⚡ 本次限制处理前 {limit} 条（共 {total_pending} 条待处理）")

    # 2. 逐条处理
    results = []
    for note in pending:
        result = process_note(note, dry_run=dry_run)
        results.append(result)
        time.sleep(2)   # 避免 API 过载

    # 3. 汇总输出
    success_count = sum(1 for r in results if r["success"])
    print("\n" + "=" * 55)
    print(f"✅ Inbox Processor 完成：{success_count}/{len(results)} 处理成功")
    print("=" * 55)

    # 4. Telegram 推送
    if not dry_run:
        tg_text = build_telegram_report(results, total_pending)
        ok = send_message(tg_text)
        if ok:
            print("📨 Telegram 推送成功")
        else:
            print("⚠️  Telegram 推送失败")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity Inbox Processor")
    parser.add_argument("--dry-run", action="store_true", help="只扫描，不实际处理")
    parser.add_argument("--limit",   type=int, default=0,  help="本次最多处理几条（0=全部）")
    args = parser.parse_args()

    main(dry_run=args.dry_run, limit=args.limit)
