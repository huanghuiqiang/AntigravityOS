"""
inbox_processor.py
──────────────────
Antigravity OS | Inbox 消费者 Agent

职责：
  1. 扫描 Obsidian 00_Inbox 中 status=pending 且 score >= 8.0 的笔记
  2. 对每篇文章调用 NotebookLM 生成深度 Report
  3. 将 NotebookLM 报告追加到原笔记
  4. 更新 frontmatter: status → done
  5. 将处理完的笔记归档到日期文件夹
  6. 推送 Telegram 通知

触发方式：
  - cron 定时：每天 10:30
  - 手动：python -m agents.inbox_processor.inbox_processor [--dry-run]
"""

import os
import json
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

from agos.config import min_score_threshold
from agos.notify import send_message

from skills.obsidian_bridge.bridge import (
    scan_pending,
    update_frontmatter,
    append_note,
    move_to_dated_folder,
    get_vault,
)

# ── 配置 ──────────────────────────────────────────────────────────
MIN_SCORE = float(os.getenv("INBOX_MIN_SCORE", str(min_score_threshold())))
NLM_TIMEOUT = int(os.getenv("NLM_TIMEOUT", "900"))
ARCHIVE_DONE = os.getenv("INBOX_ARCHIVE_DONE", "true").lower() == "true"

# ── NotebookLM 集成 ───────────────────────────────────────────────
def _warn(scope: str, detail: str):
    print(f"    ⚠️ [{scope}] {detail}")


def _set_error(result: dict, error_type: str, message: str, note_path: str = "", source_url: str = "") -> dict:
    result["success"] = False
    result["error"] = message
    result["error_type"] = error_type
    result["note_path"] = note_path
    result["source_url"] = source_url
    return result


def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    """运行子命令，返回 (returncode, stdout, stderr)。"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired as e:
        return 2, "", f"命令超时({timeout}s): {' '.join(cmd)} | {e}"
    except FileNotFoundError:
        return 127, "", f"命令不存在: {cmd[0]}"
    except Exception as e:
        return 1, "", f"命令执行异常: {' '.join(cmd)} | {e}"


def process_with_notebooklm(title: str, source_url: str, note_path: str) -> dict:
    """
    对单篇文章：
      1. 创建 NotebookLM notebook
      2. 添加 source（URL）
      3. 等待 source 处理完毕
      4. 生成 study-guide 报告
      5. 等待生成完成
      6. 下载报告内容
    """
    result = {
        "success": False,
        "notebook_id": "",
        "report": "",
        "error": "",
        "error_type": "",
        "note_path": note_path,
        "source_url": source_url,
    }

    safe_name = title[:50].replace('"', "'")
    rc, out, err = _run(["notebooklm", "create", f"Bouncer: {safe_name}", "--json"], timeout=30)
    if rc != 0:
        return _set_error(result, "notebook_create_failed", f"创建 notebook 失败: {err}", note_path, source_url)

    try:
        nb_data = json.loads(out)
        notebook_id = nb_data["id"]
        result["notebook_id"] = notebook_id
        print(f"    📓 Notebook 创建成功: {notebook_id[:8]}...")
    except (json.JSONDecodeError, KeyError) as e:
        return _set_error(result, "notebook_create_parse_failed", f"解析 notebook ID 失败: {e} | 原始输出: {out}", note_path, source_url)

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
            except (json.JSONDecodeError, KeyError) as e:
                _warn("inbox/source_add", f"解析 source 响应失败，继续后续流程: {e}")
    else:
        print(f"    ⚠️  无源 URL，直接生成报告...")

    rc, out, err = _run(
        ["notebooklm", "generate", "report",
         "--format", "study-guide",
         "--notebook", notebook_id,
         "--json"],
        timeout=60
    )
    if rc != 0:
        return _set_error(result, "report_generate_failed", f"生成报告失败: {err}", note_path, source_url)

    try:
        gen_data = json.loads(out)
        task_id = gen_data.get("task_id", "")
        print(f"    🔄 报告生成中，task_id: {task_id[:8]}...")
    except (json.JSONDecodeError, KeyError) as e:
        return _set_error(result, "report_task_parse_failed", f"解析 task_id 失败: {e}", note_path, source_url)

    rc, out, err = _run(
        ["notebooklm", "artifact", "wait", task_id,
         "--notebook", notebook_id,
         "--timeout", str(NLM_TIMEOUT)],
        timeout=NLM_TIMEOUT + 30
    )
    if rc == 2:
        return _set_error(result, "report_wait_timeout", f"报告生成超时（>{NLM_TIMEOUT}s）", note_path, source_url)
    if rc != 0:
        return _set_error(result, "report_wait_failed", f"等待报告失败: {err}", note_path, source_url)

    tmp_path = f"/tmp/nlm_report_{notebook_id[:8]}.md"
    rc, out, err = _run(
        ["notebooklm", "download", "report", tmp_path,
         "--notebook", notebook_id],
        timeout=30
    )
    if rc != 0:
        return _set_error(result, "report_download_failed", f"下载报告失败: {err}", note_path, source_url)

    try:
        report_content = Path(tmp_path).read_text(encoding="utf-8")
        result["success"] = True
        result["report"] = report_content
        print(f"    📄 报告下载成功（{len(report_content)} 字符）")
    except FileNotFoundError:
        return _set_error(result, "report_file_missing", "报告文件未找到", note_path, source_url)

    return result


# ── 主流水线 ──────────────────────────────────────────────────────

def process_note(note: dict, dry_run: bool = False) -> dict:
    """处理单个 pending 笔记。"""
    path = note["path"]
    title = note["title"]
    score = note["score"]
    source = note["source"]
    note_name = Path(path).name

    print(f"\n  🔍 处理: [{score}分] {title[:60]}")

    outcome = {
        "title": title,
        "score": score,
        "success": False,
        "notebook_id": "",
        "error": "",
        "error_type": "",
        "note_path": path,
        "source_url": source,
    }

    if dry_run:
        print(f"    [DRY RUN] 跳过实际处理")
        outcome["success"] = True
        return outcome

    nlm_result = process_with_notebooklm(title, source, path)
    outcome["notebook_id"] = nlm_result.get("notebook_id", "")
    outcome["error_type"] = nlm_result.get("error_type", "")

    if nlm_result["success"]:
        report_section = f"""
---

## 🤖 NotebookLM 深度报告

> 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}
> Notebook ID：`{nlm_result['notebook_id']}`

{nlm_result['report']}
"""
        append_note(note_name, report_section)
        update_frontmatter(note_name, {
            "status": "done",
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "notebook_id": nlm_result["notebook_id"],
        })

        if ARCHIVE_DONE:
            move_to_dated_folder(note_name)

        outcome["success"] = True
        print(f"    ✅ 处理完成并归档")
    else:
        update_frontmatter(note_name, {
            "status": "error",
            "error": nlm_result["error"][:200],
            "error_type": nlm_result.get("error_type", "unknown_error"),
        })
        outcome["error"] = nlm_result["error"]
        print(f"    ❌ 处理失败: {nlm_result['error'][:80]}")

    return outcome


def build_telegram_report(results: list[dict], total_pending: int) -> str:
    success_list = [r for r in results if r["success"]]
    fail_list = [r for r in results if not r["success"]]
    fail_type_counter = {}
    for r in fail_list:
        key = r.get("error_type", "") or "unknown_error"
        fail_type_counter[key] = fail_type_counter.get(key, 0) + 1

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
        lines.append("📌 失败类型统计：")
        for err_type, count in sorted(fail_type_counter.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"  • <code>{err_type}</code>: {count}")
        lines.append("\n⚠️ 失败条目：")
        for r in fail_list:
            e_type = r.get("error_type", "") or "unknown_error"
            lines.append(f"  ❌ [{e_type}] {r['title'][:30]} → {r['error'][:50]}")

    return "\n".join(lines)


def main(dry_run: bool = False, limit: int = 0):
    print("=" * 55)
    print("🚀 [Inbox Processor] 启动...")
    print(f"   Vault: {get_vault()}")
    print(f"   最低分数门槛: {MIN_SCORE}")
    print(f"   Dry Run: {dry_run}")
    print("=" * 55)

    pending = scan_pending(min_score=MIN_SCORE)
    total_pending = len(pending)

    if not pending:
        print("\n✅ 无 pending 条目，退出。")
        return

    if limit > 0:
        pending = pending[:limit]
        print(f"\n⚡ 本次限制处理前 {limit} 条（共 {total_pending} 条待处理）")

    results = []
    for note in pending:
        result = process_note(note, dry_run=dry_run)
        results.append(result)
        time.sleep(2)

    success_count = sum(1 for r in results if r["success"])
    print("\n" + "=" * 55)
    print(f"✅ Inbox Processor 完成：{success_count}/{len(results)} 处理成功")
    print("=" * 55)

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
    parser.add_argument("--limit", type=int, default=0, help="本次最多处理几条（0=全部）")
    args = parser.parse_args()

    main(dry_run=args.dry_run, limit=args.limit)
