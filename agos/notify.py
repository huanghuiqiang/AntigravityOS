"""
agos.notify
──────────────────
系统通知统一入口，支持路由、去重、冷却窗口与启动静默。
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

from agos.config import (
    feishu_bot_secret,
    feishu_bot_webhook,
    log_dir,
    notify_dedup_db_file,
    notify_default_cooldown_minutes,
    notify_provider,
    notify_startup_silence_minutes,
    notify_system_alerts_enabled,
    telegram_bot_token,
    telegram_chat_id,
)
from skills.feishu_bot_sender import FeishuBotSendError, send_feishu_webhook

_START_TS = int(time.time())
_AUDIT_LOG_FILE = log_dir() / "notify_audit.log"


def _now_ts() -> int:
    return int(time.time())


def _dedup_db() -> Path:
    db_path = notify_dedup_db_file()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_dedup_db())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_events (
            event_key TEXT PRIMARY KEY,
            last_state TEXT NOT NULL,
            last_sent_at INTEGER NOT NULL,
            last_channel TEXT NOT NULL,
            last_trace_id TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _audit(payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=False)
    with _AUDIT_LOG_FILE.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def _in_startup_silence() -> bool:
    silence_seconds = notify_startup_silence_minutes() * 60
    if silence_seconds <= 0:
        return False
    return (_now_ts() - _START_TS) < silence_seconds


def _send_telegram(text: str) -> bool:
    token = telegram_bot_token()
    cid = telegram_chat_id()
    if not token:
        print("  ⚠️  [Telegram] 未配置 Bot Token，跳过推送")
        return False
    if not cid:
        print("  ⚠️  [Telegram] 未配置 Chat ID，跳过推送")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
    except Exception as exc:
        print(f"  ❌ [Telegram] 异常: {exc}")
        return False
    if resp.status_code == 200 and resp.json().get("ok"):
        return True
    print(f"  ❌ [Telegram] HTTP {resp.status_code}: {resp.text}")
    return False


def _send_feishu(text: str) -> bool:
    webhook = feishu_bot_webhook()
    if not webhook:
        print("  ⚠️  [Feishu] 未配置 FEISHU_BOT_WEBHOOK，跳过推送")
        return False
    try:
        send_feishu_webhook(
            webhook=webhook,
            secret=feishu_bot_secret(),
            payload={"msg_type": "text", "content": {"text": text}},
        )
        return True
    except FeishuBotSendError as exc:
        print(f"  ❌ [Feishu] 发送失败: {exc}")
        return False


def _route_send(text: str) -> tuple[bool, str]:
    provider = notify_provider()
    if provider == "none":
        return False, "none"
    if provider == "telegram":
        return _send_telegram(text), "telegram"
    return _send_feishu(text), "feishu"


def send_message(
    text: str,
    chat_id: str | None = None,
    parse_mode: str = "HTML",
) -> bool:
    """
    兼容旧调用：仅发送 Telegram，不参与系统级去重。
    """
    token = telegram_bot_token()
    cid = chat_id or telegram_chat_id()
    if not token:
        print("  ⚠️  [Telegram] 未配置 Bot Token，跳过推送")
        return False
    if not cid:
        print("  ⚠️  [Telegram] 未配置 Chat ID，跳过推送")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": cid,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=15,
        )
    except Exception as exc:
        print(f"  ❌ [Telegram] 异常: {exc}")
        return False

    if resp.status_code == 200 and resp.json().get("ok"):
        return True
    print(f"  ❌ [Telegram] HTTP {resp.status_code}: {resp.text}")
    return False


def send_system_alert(
    *,
    event_key: str,
    level: str,
    text: str,
    meta: dict[str, str] | None = None,
) -> bool:
    if not notify_system_alerts_enabled():
        _audit(
            {
                "ts": _now_ts(),
                "event_key": event_key,
                "level": level,
                "status": "suppressed_global_switch",
            }
        )
        return False

    if _in_startup_silence():
        _audit(
            {
                "ts": _now_ts(),
                "event_key": event_key,
                "level": level,
                "status": "suppressed_startup_silence",
            }
        )
        return False

    payload_meta = meta or {}
    state = payload_meta.get("state", "fail")
    trace_id = payload_meta.get("trace_id", "")
    component = payload_meta.get("component", "unknown")
    cooldown_sec = notify_default_cooldown_minutes() * 60

    dedup_hit = False
    conn = _connect_db()
    try:
        row = conn.execute(
            "SELECT last_state, last_sent_at FROM alert_events WHERE event_key = ?",
            (event_key,),
        ).fetchone()
        now_ts = _now_ts()
        should_send = True
        if row is not None:
            last_state = str(row[0])
            last_sent_at = int(row[1])
            if state == last_state and (now_ts - last_sent_at) < cooldown_sec:
                should_send = False
                dedup_hit = True

        if not should_send:
            _audit(
                {
                    "ts": now_ts,
                    "component": component,
                    "event_key": event_key,
                    "level": level,
                    "status": "suppressed_dedup",
                    "state": state,
                    "trace_id": trace_id,
                    "dedup_hit": True,
                }
            )
            return False

        ok, channel = _route_send(text)
        conn.execute(
            """
            INSERT INTO alert_events(event_key, last_state, last_sent_at, last_channel, last_trace_id, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_key) DO UPDATE SET
                last_state=excluded.last_state,
                last_sent_at=excluded.last_sent_at,
                last_channel=excluded.last_channel,
                last_trace_id=excluded.last_trace_id,
                updated_at=excluded.updated_at
            """,
            (event_key, state, now_ts, channel, trace_id, now_ts),
        )
        conn.commit()
        _audit(
            {
                "ts": now_ts,
                "component": component,
                "event_key": event_key,
                "level": level,
                "status": "sent" if ok else "send_failed",
                "state": state,
                "trace_id": trace_id,
                "channel": channel,
                "dedup_hit": dedup_hit,
            }
        )
        return ok
    finally:
        conn.close()


def list_recent_alert_events(limit: int = 20) -> list[dict[str, str | int]]:
    conn = _connect_db()
    try:
        rows = conn.execute(
            """
            SELECT event_key, last_state, last_sent_at, last_channel, last_trace_id, updated_at
            FROM alert_events
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ).fetchall()
        out: list[dict[str, str | int]] = []
        for row in rows:
            out.append(
                {
                    "event_key": str(row[0]),
                    "last_state": str(row[1]),
                    "last_sent_at": int(row[2]),
                    "last_channel": str(row[3]),
                    "last_trace_id": str(row[4]),
                    "updated_at": int(row[5]),
                }
            )
        return out
    finally:
        conn.close()


def clear_alert_events(event_key: str | None = None) -> int:
    conn = _connect_db()
    try:
        if event_key:
            cursor = conn.execute("DELETE FROM alert_events WHERE event_key = ?", (event_key,))
        else:
            cursor = conn.execute("DELETE FROM alert_events")
        conn.commit()
        return int(cursor.rowcount)
    finally:
        conn.close()


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
