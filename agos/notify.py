"""
agos.notify
──────────────────
Telegram 推送的唯一入口。
消灭其他 agent 通过 sys.path.insert hack 引用 bouncer/telegram_notify.py 的反模式。
"""
from __future__ import annotations

import requests  # type: ignore[import-untyped]

from agos.config import telegram_bot_token, telegram_chat_id


def send_message(
    text: str,
    chat_id: str | None = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    发送消息到 Telegram。

    Args:
        text:       消息内容（支持 HTML 标签）
        chat_id:    目标 Chat ID（不传则从配置读取）
        parse_mode: "HTML" 或 "MarkdownV2"

    Returns:
        True = 发送成功
    """
    try:
        token = telegram_bot_token()
        cid = chat_id or telegram_chat_id()

        if not token:
            print("  ⚠️  [Telegram] 未配置 Bot Token，跳过推送")
            return False
        if not cid:
            print("  ⚠️  [Telegram] 未配置 Chat ID，跳过推送")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": cid,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=15,
        )

        if resp.status_code == 200 and resp.json().get("ok"):
            return True
        else:
            print(f"  ❌ [Telegram] HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"  ❌ [Telegram] 异常: {e}")
        return False


def send_bouncer_report(golden_articles: list, total_scanned: int) -> bool:
    """发送 Cognitive Bouncer 的巡逻报告。"""
    if not golden_articles:
        text = (
            "🤖 <b>Cognitive Bouncer 巡逻完毕</b>\n\n"
            f"📊 共扫描 <b>{total_scanned}</b> 篇文章\n"
            "🗑️ 无高密度内容，全部过滤。"
        )
        return send_message(text)

    lines = [
        "🤖 <b>Cognitive Bouncer 报告</b>",
        f"📊 扫描 <b>{total_scanned}</b> 篇 → 挖出 <b>{len(golden_articles)}</b> 颗金子\n",
    ]

    for idx, art in enumerate(golden_articles, 1):
        score = art.get("score", 0)
        title = art.get("title", "Unknown")
        url = art.get("url", "")
        axiom = art.get("axiom", "")

        if score >= 9.5:
            medal = "💎"
        elif score >= 9.0:
            medal = "🏆"
        elif score >= 8.5:
            medal = "🥇"
        else:
            medal = "⭐️"

        lines.append(f"{medal} <b>Top {idx}</b> [{score:.1f}分]")
        lines.append(f'📰 <a href="{url}">{title}</a>')
        if axiom:
            lines.append(f"🧠 <i>{axiom}</i>")
        lines.append("")

    return send_message("\n".join(lines))


def send_bouncer_dedup_alert(
    *,
    dedup_rate: float,
    deduped_count: int,
    fetched_count: int,
    trace_id: str,
    by_feed_lines: list[str],
) -> bool:
    feed_text = "\n".join(by_feed_lines) if by_feed_lines else "无 feed 细分数据"
    text = (
        "⚠️ <b>Cognitive Bouncer 去重率告警</b>\n\n"
        f"去重率: <b>{dedup_rate:.2f}%</b>\n"
        f"去重数: <b>{deduped_count}</b> / 抓取数: <b>{fetched_count}</b>\n"
        f"trace_id: <code>{trace_id}</code>\n\n"
        f"{feed_text}"
    )
    return send_message(text)
