import httpx
import pytest
import json

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from skills.feishu_bridge.bridge import BridgeConfig, FeishuDocBridge
from skills.feishu_bridge.main import app


def test_refresh_token_after_401() -> None:
    calls = {"auth": 0, "doc": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            calls["auth"] += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "new-token", "expire": 7200})

        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1"):
            calls["doc"] += 1
            if calls["doc"] == 1:
                return httpx.Response(401, json={"code": 99991661, "msg": "unauthorized"})
            return httpx.Response(200, json={"code": 0, "data": {"document": {"title": "Bridge"}}})

        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "stale-token"
    bridge._token_expire_at = 9999999999

    result = bridge.health()

    assert result["success"] is True
    assert result["title"] == "Bridge"
    assert calls["auth"] == 1
    assert calls["doc"] == 2


def test_retry_on_429() -> None:
    attempts = {"doc": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1"):
            attempts["doc"] += 1
            if attempts["doc"] < 3:
                return httpx.Response(429, json={"code": 0, "msg": "rate limited"})
            return httpx.Response(200, json={"code": 0, "data": {"document": {"title": "Ready"}}})
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1", retry_delay_seconds=0)
    bridge = FeishuDocBridge(cfg, client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.health()

    assert result["success"] is True
    assert attempts["doc"] == 3


def test_find_section_block_id() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/content"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "block_id": "b-1",
                                "heading1": {
                                    "elements": [
                                        {"text_run": {"content": "每日进度日志"}},
                                    ]
                                },
                            },
                            {
                                "block_id": "b-2",
                                "text": {
                                    "elements": [
                                        {"text_run": {"content": "正文"}},
                                    ]
                                },
                            },
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    assert bridge._find_section_block_id("每日进度日志") == "b-1"
    assert bridge._find_section_block_id("不存在") is None


def test_health_returns_error_payload_when_env_missing(monkeypatch) -> None:
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]


def test_read_doc_returns_error_payload_when_env_missing(monkeypatch) -> None:
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post("/read_doc", json={"format": "markdown"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]


def test_update_bitable_patch_success() -> None:
    calls = {"patch": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records/rec_x"):
            assert req.method == "PATCH"
            calls["patch"] += 1
            assert json.loads(req.content.decode("utf-8")) == {"fields": {"Status": "Done"}}
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "record": {
                            "record_id": "rec_x",
                            "fields": {"Status": "Done"},
                        }
                    },
                },
            )
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.update_bitable(
        app_token="app_x",
        table_id="tbl_x",
        record_id="rec_x",
        fields={"Status": "Done"},
    )
    assert result["success"] is True
    assert result["record_id"] == "rec_x"
    assert calls["patch"] == 1


def test_update_bitable_fallback_to_put_on_patch_error() -> None:
    calls = {"patch": 0, "put": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records/rec_x"):
            if req.method == "PATCH":
                calls["patch"] += 1
                return httpx.Response(200, json={"code": 1254003, "msg": "method not allowed"})
            if req.method == "PUT":
                calls["put"] += 1
                return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "rec_x"}}})
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.update_bitable(
        app_token="app_x",
        table_id="tbl_x",
        record_id="rec_x",
        fields={"Status": "Done"},
    )
    assert result["success"] is True
    assert calls["patch"] == 1
    assert calls["put"] == 1


def test_update_bitable_endpoint_returns_error_payload_when_env_missing(monkeypatch) -> None:
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post(
        "/update_bitable",
        json={
            "app_token": "app_x",
            "table_id": "tbl_x",
            "record_id": "rec_x",
            "fields": {"Status": "Done"},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]
