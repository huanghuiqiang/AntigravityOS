from __future__ import annotations

import httpx
import pytest
import json

from skills.feishu_bot_sender.sender import build_feishu_signature, send_feishu_webhook, FeishuBotSendError


def test_build_signature_non_empty() -> None:
    sign = build_feishu_signature("abc", "1700000000")
    assert isinstance(sign, str)
    assert len(sign) > 10


def test_send_webhook_success() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        payload = json.loads(req.content.decode("utf-8"))
        assert payload["msg_type"] == "text"
        return httpx.Response(200, json={"code": 0, "msg": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = send_feishu_webhook(
            webhook="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx",
            payload={"msg_type": "text", "content": {"text": "hello"}},
            client=client,
        )
    finally:
        client.close()
    assert result["code"] == 0


def test_send_webhook_non_zero_code_raises() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        _ = req
        return httpx.Response(200, json={"code": 19022, "msg": "keyword not match"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(FeishuBotSendError):
            send_feishu_webhook(
                webhook="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx",
                payload={"msg_type": "text", "content": {"text": "hello"}},
                client=client,
            )
    finally:
        client.close()
