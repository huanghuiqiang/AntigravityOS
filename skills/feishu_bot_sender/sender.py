from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any

import httpx


class FeishuBotSendError(RuntimeError):
    pass


def build_feishu_signature(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    hmac_code = hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _redact_webhook(webhook: str) -> str:
    if "/hook/" not in webhook:
        return "<invalid-webhook>"
    prefix, _, tail = webhook.partition("/hook/")
    masked = "***" if len(tail) > 3 else "*"
    return f"{prefix}/hook/{masked}"


def send_feishu_webhook(
    *,
    webhook: str,
    payload: dict[str, Any],
    secret: str = "",
    timeout_sec: float = 10.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not webhook:
        raise FeishuBotSendError("FEISHU_BOT_WEBHOOK 未配置")

    request_payload: dict[str, Any] = dict(payload)
    if secret:
        timestamp = str(int(time.time()))
        request_payload["timestamp"] = timestamp
        request_payload["sign"] = build_feishu_signature(secret, timestamp)

    close_client = client is None
    active_client = client or httpx.Client(timeout=timeout_sec)
    try:
        resp = active_client.post(webhook, json=request_payload)
        if resp.status_code != 200:
            raise FeishuBotSendError(f"飞书 webhook HTTP {resp.status_code}: {_redact_webhook(webhook)}")

        data = resp.json()
        if not isinstance(data, dict):
            raise FeishuBotSendError("飞书 webhook 返回格式异常")

        code = data.get("code")
        if code != 0:
            msg = str(data.get("msg", "unknown error"))
            raise FeishuBotSendError(f"飞书 webhook code={code} msg={msg}")
        return data
    except httpx.TimeoutException as exc:
        raise FeishuBotSendError(f"飞书 webhook 超时: {_redact_webhook(webhook)}") from exc
    except httpx.HTTPError as exc:
        raise FeishuBotSendError(f"飞书 webhook 请求失败: {_redact_webhook(webhook)}") from exc
    finally:
        if close_client:
            active_client.close()
