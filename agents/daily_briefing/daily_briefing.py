"""
daily_briefing.py
──────────────────────────────────────────────────────────────────
Antigravity OS  |  Daily Briefing Agent

职责：每天早上推送一份 Telegram 早报，包含：
  1. 📊 Pipeline 状态快照（pending/done/error 计数）
  2. ⭐ 今日/昨日高分 Top5（按分数排序）
  3. 🚦 Cron 健康状态（Bouncer 是否按时跑过）
  4. 📈 7天入库趋势（spark 迷你图）
  5. 🎯 一句话"今日重点"（pending 最高分文章标题）

Cron 建议：07:50，在 Bouncer(08:00) 之前推送
  50 7 * * *  cd ROOT && PYTHONPATH=. python agents/daily_briefing/daily_briefing.py

触发方式：
  - 手动：PYTHONPATH=. python agents/daily_briefing/daily_briefing.py
  - 可加 --mock 在没有真实数据时生成示例报告（用于测试）
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

_THIS_DIR = Path(__file__).parent
_ROOT     = _THIS_DIR.parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.stats import collect

_BOUNCER_DIR = _ROOT / "agents/cognitive_bouncer"
sys.path.insert(0, str(_BOUNCER_DIR))
from telegram_notify import send_message


# ── 格式化工具 ────────────────────────────────────────────────────

def sparkline(values: list[int]) -> str:
    """将整数列表转为 Unicode 迷你折线。"""
    bars = " ▁▂▃▄▅▆▇█"
    if not values or max(values) == 0:
        return "─" * len(values)
    m = max(values)
    return "".join(bars[min(int(v / m * 8), 8)] for v in values)


def health_emoji(score: float) -> str:
    if score >= 80: return "🟢"
    if score >= 50: return "🟡"
    return "🔴"


def score_medal(score: float) -> str:
    if score >= 9.5: return "💎"
    if score >= 9.0: return "🏆"
    if score >= 8.5: return "🥇"
    return "⭐️"


def fmt_cron_time(dt) -> str:
    if not dt:
        return "❌ 从未运行"
    delta = datetime.now() - dt
    h = delta.total_seconds() / 3600
    status = "✅" if h < 25 else "⚠️"
    return f"{status} {dt.strftime('%H:%M')} ({h:.0f}h 前)"


# ── 报告生成 ──────────────────────────────────────────────────────

def build_report(r) -> str:
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekday_names[datetime.now().weekday()]

    # ── Header ───────────────────────────────────────────────────
    lines = [
        f"🌅 <b>Antigravity OS — 今日早报</b>",
        f"<code>{today} ({weekday}曜日)</code>",
        "",
    ]

    # ── 1. Pipeline 快照 ─────────────────────────────────────────
    he = health_emoji(r.health_score)
    lines += [
        f"{he} <b>系统健康度 {r.health_score:.0f}/100</b>",
        f"📥 总入库 <b>{r.total}</b>  |  "
        f"⏳ Pending <b>{r.pending}</b>  |  "
        f"✅ Done <b>{r.done}</b>  |  "
        f"❌ Error <b>{r.error}</b>",
    ]
    if r.bottleneck and r.health_score < 80:
        lines.append(f"⚡ 瓶颈: {r.bottleneck}")
    lines.append("")

    # ── 2. 今日 Top 5 高分（pending 优先）────────────────────────
    today_notes = sorted(
        [n for n in r.notes if n.created in (today, yesterday)],
        key=lambda n: n.score, reverse=True,
    )[:5]

    if today_notes:
        lines.append("🔥 <b>今日高价值入库 Top 5</b>")
        for n in today_notes:
            from urllib.parse import urlparse
            medal = score_medal(n.score)
            title = (n.title or n.filename)[:45]
            host  = urlparse(n.source).netloc[:20] if n.source else "─"
            tag   = "Clip" if n.is_clip else "RSS"
            lines.append(
                f"  {medal} [{n.score:.1f}] <a href=\"{n.source}\">{title}</a>"
                f" <code>{tag}·{host}</code>"
            )
        lines.append("")
    elif r.pending > 0:
        # 如果今天没新文章，显示 pending 最高分
        top_pending = sorted(
            [n for n in r.notes if n.status == "pending"],
            key=lambda n: n.score, reverse=True,
        )[:3]
        if top_pending:
            lines.append("⏳ <b>待处理高分（积压）</b>")
            for n in top_pending:
                medal = score_medal(n.score)
                title = (n.title or n.filename)[:45]
                lines.append(f"  {medal} [{n.score:.1f}] {title}")
            lines.append("")

    # ── 3. Cron 状态 ─────────────────────────────────────────────
    lines += [
        "⏰ <b>Cron 状态</b>",
        f"  🤖 Bouncer:        {fmt_cron_time(r.last_bouncer_run)}",
        f"  🧠 InboxProcessor: {fmt_cron_time(r.last_inbox_run)}",
        "",
    ]

    # ── 4. 7天趋势 ───────────────────────────────────────────────
    spark_in   = sparkline(r.bouncer_7day)
    spark_done = sparkline(r.throughput_7day)
    total_in   = sum(r.bouncer_7day)
    total_done = sum(r.throughput_7day)

    lines += [
        "📊 <b>本周趋势（7天）</b>",
        f"  入库: <code>{spark_in}</code>  {total_in} 条",
        f"  完成: <code>{spark_done}</code>  {total_done} 条",
        "",
    ]

    # ── 5. 今日重点 ──────────────────────────────────────────────
    top_today_pending = [n for n in r.notes
                         if n.status == "pending" and n.score >= 9.0]
    if top_today_pending:
        top = max(top_today_pending, key=lambda n: n.score)
        lines += [
            "🎯 <b>今日重点（最高分 pending）</b>",
            f"  {score_medal(top.score)} [{top.score:.1f}] "
            f"<a href=\"{top.source}\">{(top.title or top.filename)[:50]}</a>",
            "",
        ]

    # ── Footer ───────────────────────────────────────────────────
    lines += [
        "─────────────────────",
        f"<i>Antigravity OS · {datetime.now().strftime('%H:%M')}</i>",
    ]

    return "\n".join(lines)


# ── 入口 ─────────────────────────────────────────────────────────

def main(mock: bool = False):
    print(f"🌅 [Daily Briefing] 生成早报... {datetime.now().strftime('%H:%M')}")

    r = collect()

    if mock and r.total == 0:
        # 测试模式：注入假数据
        print("  [mock] 注入示例数据")
        r.total   = 42
        r.pending = 7
        r.done    = 33
        r.error   = 2
        r.health_score = 85.0
        r.bottleneck   = "✅ 系统运行正常"
        r.bouncer_7day      = [3, 5, 8, 12, 6, 9, 7]
        r.throughput_7day   = [0, 0, 3, 8,  4, 6, 5]
        r.last_bouncer_run  = datetime.now() - __import__("datetime").timedelta(hours=2)
        r.score_dist        = {"9-10": 8, "8-9": 25, "7-8": 9, "<7": 0}

    report = build_report(r)

    print("📨 推送 Telegram...")
    ok = send_message(report)

    if ok:
        print("✅ Daily Briefing 推送成功")
    else:
        print("⚠️  推送失败（检查 Telegram 配置）")
        # 本地输出 fallback
        print("\n" + "─" * 40)
        print(report.replace("<b>", "").replace("</b>", "")
              .replace("<i>", "").replace("</i>", "")
              .replace("<code>", "").replace("</code>", ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity Daily Briefing")
    parser.add_argument("--mock", action="store_true", help="注入示例数据（测试用）")
    args = parser.parse_args()
    main(mock=args.mock)
