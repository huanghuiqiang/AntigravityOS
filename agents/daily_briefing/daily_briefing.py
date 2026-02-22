"""
daily_briefing.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Daily Briefing Agent
"""

import argparse
from datetime import datetime, timedelta
from urllib.parse import urlparse

from scripts.stats import collect
from agos.config import backlog_threshold_days
from agos.notify import send_message


BACKLOG_THRESHOLD_DAYS = backlog_threshold_days()


# ── 格式化工具 ────────────────────────────────────────────────────

def sparkline(values: list[int]) -> str:
    bars = " ▁▂▃▄▅▆▇█"
    if not values or max(values) == 0:
        return "─" * 7
    m = max(values)
    return "".join(bars[min(int(v / m * 8), 8)] for v in values)

def health_emoji(score: float) -> str:
    if score >= 85: return "🟢"
    if score >= 60: return "🟡"
    return "🔴"

def score_medal(score: float) -> str:
    if score >= 9.5: return "💎"
    if score >= 9.0: return "🏆"
    if score >= 8.5: return "🥇"
    return "⭐️"

def fmt_cron_time(dt) -> str:
    if not dt: return "❌ 从未运行"
    delta = datetime.now() - dt
    h = delta.total_seconds() / 3600
    status = "✅" if h < 26 else "⚠️"
    return f"{status} {dt.strftime('%H:%M')} ({h:.0f}h 前)"


# ── 报告生成 ──────────────────────────────────────────────────────

def build_report(r) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_names[datetime.now().weekday()]

    # ── 1. 健康分析 & 审计警报 ───────────────────────────────────
    he = health_emoji(r.health_score)
    health_text = f"{he} <b>系统健康度 {r.health_score:.0f}/100</b>"

    alerts = []
    if r.orphan_axioms:
        alerts.append(f"🕸 <b>知识孤岛</b>：{len(r.orphan_axioms)} 条公理未被引用")
    if r.backlog_issues:
        alerts.append(
            f"⏳ <b>积压警报</b>：{len(r.backlog_issues)} 条已积压超过 {BACKLOG_THRESHOLD_DAYS} 天"
        )
    if r.error > 0:
        alerts.append(f"❌ <b>损坏条目</b>：共有 {r.error} 条错误笔记待检查")

    alert_section = ""
    if alerts:
        alert_section = "\n📢 <b>健康警报</b>\n" + "\n".join(f"  • {a}" for a in alerts) + "\n"

    # ── 2. Header ────────────────────────────────────────────────
    lines = [
        f"🌅 <b>Antigravity OS — 今日早报</b>",
        f"<code>{today} ({weekday}曜日)</code>",
        "",
        health_text,
        f"📥 总入库 <b>{r.total}</b>  |  "
        f"⏳ Pending <b>{r.pending}</b>  |  "
        f"✅ Done <b>{r.done}</b>",
    ]

    if r.bottleneck and r.health_score < 90:
        lines.append(f"⚡ 瓶颈: {r.bottleneck}")

    if alert_section:
        lines.append(alert_section)
    else:
        lines.append("")

    if r.error_types:
        lines.append("🧩 <b>失败类型 Top</b>")
        top_errors = sorted(r.error_types.items(), key=lambda x: x[1], reverse=True)[:3]
        for err_type, count in top_errors:
            lines.append(f"  • <code>{err_type}</code>: {count}")
        lines.append("")

    # ── 3. 今日/昨日 Top 5 ───────────────────────────────────────
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today_notes = sorted(
        [n for n in r.notes if n.created in (today, yesterday)],
        key=lambda n: n.score, reverse=True,
    )[:5]

    if today_notes:
        lines.append("🔥 <b>近期高价值入库</b>")
        for n in today_notes:
            medal = score_medal(n.score)
            title = (n.title or n.filename)[:40]
            host = urlparse(n.source).netloc[:20] if n.source else "─"
            lines.append(f'  {medal} [{n.score:.1f}] <a href="{n.source}">{title}</a> <code>{host}</code>')
        lines.append("")
    elif r.pending > 0:
        top_pending = sorted([n for n in r.notes if n.status == "pending"], key=lambda n: n.score, reverse=True)[:3]
        if top_pending:
            lines.append("⏳ <b>待处理积压 (Top 3)</b>")
            for n in top_pending:
                lines.append(f"  {score_medal(n.score)} [{n.score:.1f}] {n.title[:40]}")
            lines.append("")

    # ── 4. Cron & 7d 趋势 ────────────────────────────────────────
    lines += [
        "⏰ <b>Cron 状态</b>",
        f"  🤖 Bouncer: {fmt_cron_time(r.last_bouncer_run)}",
        f"  🧠 Inbox:   {fmt_cron_time(r.last_inbox_run)}",
        "",
        "📊 <b>本周趋势（7天）</b>",
        f"  入库: <code>{sparkline(r.bouncer_7day)}</code>  {sum(r.bouncer_7day)} 条",
        f"  完成: <code>{sparkline(r.throughput_7day)}</code>  {sum(r.throughput_7day)} 条",
        "",
    ]

    # ── 5. 合成建议 ────────────────────────────────────────────
    pending_high = [n for n in r.notes if n.status == "pending" and n.score >= 9.0]

    if pending_high:
        top = max(pending_high, key=lambda n: n.score)
        lines += [
            "🎯 <b>今日重点阅读</b>",
            f'  {score_medal(top.score)} [{top.score:.1f}] <a href="{top.source}">{(top.title or top.filename)[:50]}</a>',
            "",
        ]

    lines += [
        "─────────────────────",
        f"<i>Antigravity OS · {datetime.now().strftime('%H:%M')}</i>",
    ]

    return "\n".join(lines)


def main(mock: bool = False):
    print(f"🌅 [Daily Briefing] 生成早报...")
    r = collect()

    if mock and r.total == 0:
        r.total, r.pending, r.done, r.health_score = 50, 5, 45, 92.0
        r.bouncer_7day, r.throughput_7day = [2, 4, 6, 8, 5, 7, 3], [1, 2, 4, 5, 3, 5, 2]
        r.last_bouncer_run = datetime.now() - timedelta(hours=2)

    report = build_report(r)
    if send_message(report):
        print("✅ Daily Briefing 推送成功")
    else:
        print("⚠️ 推送失败，本地输出：\n" + report.replace("<b>", "").replace("</b>", ""))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    main(mock=parser.parse_args().mock)
