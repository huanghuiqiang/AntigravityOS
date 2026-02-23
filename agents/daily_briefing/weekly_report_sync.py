"""
weekly_report_sync.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Weekly Feishu Report Sync
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

from scripts.stats import collect
from skills.feishu_bridge import FeishuBridgeError, build_bridge_from_env


def _week_range(today: datetime | None = None) -> tuple[str, str]:
    now = today or datetime.now()
    start = now - timedelta(days=6)
    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def _build_weekly_markdown(r, *, today: datetime | None = None) -> str:
    start, end = _week_range(today)
    lines = [
        f"# Antigravity 周报（{start} ~ {end}）",
        "",
        "## 关键指标",
        f"- 系统健康度：{r.health_score:.0f}/100",
        f"- 总入库：{r.total}",
        f"- 待处理：{r.pending}",
        f"- 已完成：{r.done}",
        f"- 错误条目：{r.error}",
        f"- 7日入库总量：{sum(r.bouncer_7day)}",
        f"- 7日完成总量：{sum(r.throughput_7day)}",
    ]
    if r.bottleneck:
        lines.append(f"- 当前瓶颈：{r.bottleneck}")
    if r.error_types:
        top_errors = sorted(r.error_types.items(), key=lambda x: x[1], reverse=True)[:5]
        lines.append("")
        lines.append("## 错误类型 Top")
        for err_type, count in top_errors:
            lines.append(f"- `{err_type}`: {count}")
    return "\n".join(lines)


def sync_weekly_report(*, bridge=None, today: datetime | None = None) -> dict:
    if os.getenv("FEISHU_WEEKLY_REPORT_ENABLED", "true").strip().lower() in {"0", "false", "off"}:
        return {"success": False, "message": "FEISHU_WEEKLY_REPORT_ENABLED=false，跳过同步"}

    r = collect()
    start, end = _week_range(today)
    title = f"周报 - {start} ~ {end}"
    section_title = os.getenv("FEISHU_WEEKLY_SECTION", "5. 周报 & 复盘区（留空，Claude以后生成）").strip()
    created_bridge = False
    active_bridge = bridge

    try:
        if active_bridge is None:
            active_bridge = build_bridge_from_env()
            created_bridge = True

        created = active_bridge.create_sub_doc(title=title)
        weekly_doc_id = created["document_id"]
        weekly_url = created.get("url", "")

        markdown = _build_weekly_markdown(r, today=today)
        active_bridge.append_markdown(markdown, document_id=weekly_doc_id)
        active_bridge.append_markdown(
            f"- [{title}]({weekly_url})\n  - 健康度 {r.health_score:.0f}/100，入库 {r.total}，完成 {r.done}，待处理 {r.pending}",
            section_title=section_title or None,
        )
        return {
            "success": True,
            "title": title,
            "document_id": weekly_doc_id,
            "url": weekly_url,
        }
    except FeishuBridgeError as exc:
        return {"success": False, "message": str(exc)}
    finally:
        if created_bridge:
            active_bridge.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        r = collect()
        print(_build_weekly_markdown(r))
        return 0

    result = sync_weekly_report()
    if result.get("success"):
        print(f"✅ 周报同步成功: {result.get('url')}")
        return 0
    print(f"⚠️ 周报同步失败: {result.get('message')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
