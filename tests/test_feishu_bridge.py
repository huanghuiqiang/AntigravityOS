import httpx
import pytest
import json

try:
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    TestClient = None
    FASTAPI_AVAILABLE = False

from skills.feishu_bridge.bridge import BridgeConfig, FeishuAPIError, FeishuDocBridge
if FASTAPI_AVAILABLE:
    from skills.feishu_bridge.main import app
else:  # pragma: no cover - environment dependent
    app = None


@pytest.fixture(autouse=True)
def _reset_bridge_singleton():
    if not FASTAPI_AVAILABLE:
        yield
        return

    from skills.feishu_bridge import main as main_module

    main_module._bridge_singleton = None
    yield
    main_module._bridge_singleton = None


def test_auth_error_preserves_feishu_error_details() -> None:
    calls = {"doc": 0, "auth": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            calls["auth"] += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "fresh-token", "expire": 7200})
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1"):
            calls["doc"] += 1
            return httpx.Response(
                403,
                json={
                    "code": 99991672,
                    "msg": "Access denied",
                    "error": {"log_id": "log_x_123"},
                },
            )
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "stale"
    bridge._token_expire_at = 9999999999

    with pytest.raises(Exception) as exc:
        bridge.health()
    msg = str(exc.value)
    assert "鉴权失败: 403" in msg
    assert "code=99991672" in msg
    assert "Access denied" in msg
    assert "log_id=log_x_123" in msg
    assert "trace_id=" in msg
    assert calls["doc"] == 2
    assert calls["auth"] == 1


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
        if req.url.path.endswith("/open-apis/docx/v1/documents/convert"):
            return httpx.Response(200, json={"code": 0, "data": {"blocks": [{"block_type": 2}]}})
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            return httpx.Response(200, json={"code": 0, "data": {"items": []}})

        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "stale-token"
    bridge._token_expire_at = 9999999999

    result = bridge.health()

    assert result["success"] is True
    assert result["title"] == "Bridge"
    assert calls["auth"] == 1
    assert calls["doc"] == 3


def test_retry_on_429() -> None:
    attempts = {"doc": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1"):
            attempts["doc"] += 1
            if attempts["doc"] < 3:
                return httpx.Response(429, json={"code": 0, "msg": "rate limited"})
            return httpx.Response(200, json={"code": 0, "data": {"document": {"title": "Ready"}}})
        if req.url.path.endswith("/open-apis/docx/v1/documents/convert"):
            return httpx.Response(200, json={"code": 0, "data": {"blocks": [{"block_type": 2}]}})
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            return httpx.Response(200, json={"code": 0, "data": {"items": []}})
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cfg = BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1", retry_delay_seconds=0)
    bridge = FeishuDocBridge(cfg, client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.health()

    assert result["success"] is True
    assert attempts["doc"] == 4


def test_find_section_block_id() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
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


def test_find_section_block_id_with_normalized_title() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "block_id": "b-4",
                                "heading1": {"elements": [{"text_run": {"content": "4. 快速任务列表"}}]},
                            }
                        ]
                    },
                },
            )
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    assert bridge._find_section_block_id("快速任务列表") == "b-4"


def test_find_section_block_id_uses_cache() -> None:
    calls = {"blocks": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            calls["blocks"] += 1
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"items": [{"block_id": "b-9", "text": {"elements": [{"text_run": {"content": "章节A"}}]}}]},
                },
            )
        raise AssertionError(f"unexpected path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    assert bridge._find_section_block_id("章节A") == "b-9"
    assert bridge._find_section_block_id("章节A") == "b-9"
    assert calls["blocks"] == 1


def test_health_returns_error_payload_when_env_missing(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 500
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]


def test_read_doc_returns_error_payload_when_env_missing(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post("/read_doc", json={"format": "markdown"})
    assert resp.status_code == 500
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


def test_update_bitable_does_not_fallback_on_auth_error() -> None:
    calls = {"patch": 0, "put": 0, "auth": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            calls["auth"] += 1
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "new-token", "expire": 7200})
        if req.url.path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records/rec_x"):
            if req.method == "PATCH":
                calls["patch"] += 1
                return httpx.Response(403, json={"code": 91403, "msg": "Forbidden"})
            if req.method == "PUT":
                calls["put"] += 1
                return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "rec_x"}}})
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    with pytest.raises(Exception) as exc:
        bridge.update_bitable(
            app_token="app_x",
            table_id="tbl_x",
            record_id="rec_x",
            fields={"Status": "Done"},
        )
    assert "403" in str(exc.value)
    assert calls["patch"] == 2
    assert calls["auth"] == 1
    assert calls["put"] == 0


def test_update_bitable_endpoint_returns_error_payload_when_env_missing(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
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
    assert resp.status_code == 500
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]


def test_create_sub_doc_success() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents"):
            assert req.method == "POST"
            assert json.loads(req.content.decode("utf-8")) == {"title": "周报 - 2026-02-22"}
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "document": {
                            "document_id": "doc_new_1",
                            "title": "周报 - 2026-02-22",
                        }
                    },
                },
            )
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.create_sub_doc("周报 - 2026-02-22")
    assert result["success"] is True
    assert result["document_id"] == "doc_new_1"
    assert "/docx/doc_new_1" in result["url"]


def test_create_sub_doc_endpoint_returns_error_payload_when_env_missing(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(main_module.FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")),
    )

    client = TestClient(app)
    resp = client.post("/create_sub_doc", json={"title": "周报 - 2026-02-22"})
    assert resp.status_code == 500
    assert resp.json()["success"] is False
    assert "未配置" in resp.json()["message"]


def test_health_returns_403_when_auth_forbidden(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    monkeypatch.setattr(
        main_module,
        "build_bridge_from_env",
        lambda: (_ for _ in ()).throw(
            FeishuAPIError(
                "鉴权失败: 403",
                status_code=403,
                error_code=99991672,
                log_id="log_x",
                trace_id="trace_x",
            )
        ),
    )

    client = TestClient(app)
    resp = client.post("/health")
    assert resp.status_code == 403
    assert resp.json()["success"] is False
    assert resp.json()["error_code"] == 99991672
    assert resp.json()["log_id"] == "log_x"
    assert resp.json()["trace_id"] == "trace_x"


def test_append_markdown_returns_400_for_empty_markdown(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    class _Bridge:
        def append_markdown(self, markdown: str, section_title: str | None = None) -> dict:
            raise main_module.FeishuBridgeError("markdown 不能为空")

        def close(self) -> None:
            return None

    monkeypatch.setattr(main_module, "build_bridge_from_env", lambda: _Bridge())

    client = TestClient(app)
    resp = client.post("/append_markdown", json={"markdown": "", "section_title": "每日进度日志"})
    assert resp.status_code == 400
    assert resp.json()["success"] is False


def test_bridge_singleton_reuses_same_instance(monkeypatch) -> None:
    if not FASTAPI_AVAILABLE:
        pytest.skip("fastapi not installed")
    from skills.feishu_bridge import main as main_module

    calls = {"build": 0}

    class _Bridge:
        def health(self):
            return {"success": True}

        def close(self):
            return None

    def _build():
        calls["build"] += 1
        return _Bridge()

    monkeypatch.setattr(main_module, "build_bridge_from_env", _build)
    client = TestClient(app)

    assert client.post("/health").status_code == 200
    assert client.post("/health").status_code == 200
    assert calls["build"] == 1


def test_append_markdown_uses_children_endpoint() -> None:
    calls = {"convert": 0, "append": 0, "blocks": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            calls["blocks"] += 1
            return httpx.Response(
                200,
                json={"code": 0, "data": {"items": [{"block_id": "root_1", "block_type": 1, "parent_id": ""}]}},
            )

        if req.url.path.endswith("/open-apis/docx/v1/documents/convert"):
            calls["convert"] += 1
            return httpx.Response(
                200,
                json={"code": 0, "data": {"blocks": [{"block_type": 2, "text": {"elements": []}}]}},
            )

        expected = "/open-apis/docx/v1/documents/doc-1/blocks/root_1/children"
        if req.url.path.endswith(expected):
            calls["append"] += 1
            return httpx.Response(
                200,
                json={"code": 0, "data": {"children": [{"block_id": "new_block_1"}]}},
            )
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.append_markdown("test line")
    assert result["success"] is True
    assert result["block_id"] == "new_block_1"
    assert calls["convert"] == 1
    assert calls["blocks"] == 1
    assert calls["append"] == 1


def test_append_markdown_raises_when_section_not_found() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            return httpx.Response(200, json={"code": 0, "data": {"items": []}})
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    with pytest.raises(Exception) as exc:
        bridge.append_markdown("line", section_title="不存在章节")
    assert "section 不存在" in str(exc.value)


def test_diagnose_permissions_with_bitable_target() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/open-apis/docx/v1/documents/doc-1"):
            return httpx.Response(200, json={"code": 0, "data": {"document": {"title": "ok"}}})
        if path.endswith("/open-apis/docx/v1/documents/convert"):
            return httpx.Response(200, json={"code": 0, "data": {"blocks": [{"block_type": 2}]}})
        if path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records") and req.method == "GET":
            return httpx.Response(
                200,
                json={"code": 0, "data": {"items": [{"record_id": "rec_1", "fields": {"Status": "进行中"}}]}},
            )
        if path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records/rec_1"):
            return httpx.Response(200, json={"code": 0, "data": {"record": {"record_id": "rec_1"}}})
        raise AssertionError(f"unexpected {req.method} path: {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.diagnose_permissions(document_id="doc-1", app_token="app_x", table_id="tbl_x")
    checks = result["checks"]
    assert checks["doc_read_ok"] is True
    assert checks["doc_write_ok"] is True
    assert checks["bitable_read_ok"] is True
    assert checks["bitable_write_ok"] is True


def test_read_doc_supports_document_override() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/open-apis/docx/v1/documents/doc-override/raw_content"):
            return httpx.Response(200, json={"code": 0, "data": {"content": "override-content"}})
        raise AssertionError(f"unexpected {req.method} path: {req.url.path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-default"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.read_doc(format_type="markdown", document_id="doc-override")
    assert result["success"] is True
    assert result["content"] == "override-content"


def test_clear_section_deletes_between_heading_boundaries() -> None:
    calls = {"delete": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/open-apis/docx/v1/documents/doc-1/blocks") and req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {"block_id": "root", "block_type": 1, "children": ["h1", "p1", "p2", "h2"]},
                            {"block_id": "h1", "block_type": 4, "heading1": {"elements": [{"text_run": {"content": "目标章节"}}]}},
                            {"block_id": "p1", "block_type": 2},
                            {"block_id": "p2", "block_type": 2},
                            {"block_id": "h2", "block_type": 4, "heading1": {"elements": [{"text_run": {"content": "下一章节"}}]}},
                        ]
                    },
                },
            )
        if path.endswith("/open-apis/docx/v1/documents/doc-1/blocks/root/children/batch_delete") and req.method == "DELETE":
            calls["delete"] += 1
            body = json.loads(req.content.decode("utf-8"))
            assert body == {"start_index": 1, "end_index": 3}
            return httpx.Response(200, json={"code": 0, "data": {}})
        raise AssertionError(f"unexpected {req.method} path: {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    result = bridge.clear_section("目标章节")
    assert result["success"] is True
    assert result["deleted_count"] == 2
    assert calls["delete"] == 1


def test_health_contains_probe_breakdown() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if path.endswith("/open-apis/docx/v1/documents/doc-1"):
            return httpx.Response(200, json={"code": 0, "data": {"document": {"title": "Bridge"}}})
        if path.endswith("/open-apis/docx/v1/documents/convert"):
            return httpx.Response(200, json={"code": 0, "data": {"blocks": [{"block_type": 2}]}})
        if path.endswith("/open-apis/docx/v1/documents/doc-1/blocks"):
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "items": [
                            {
                                "block_id": "b53",
                                "block_type": 53,
                                "reference_base": {"token": "app_x_tbl_x"},
                            }
                        ]
                    },
                },
            )
        if path.endswith("/open-apis/bitable/v1/apps/app_x/tables/tbl_x/records") and req.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": {"items": []}})
        raise AssertionError(f"unexpected {req.method} path: {path}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bridge = FeishuDocBridge(BridgeConfig(app_id="id", app_secret="secret", document_id="doc-1"), client=client)
    bridge._tenant_access_token = "token"
    bridge._token_expire_at = 9999999999

    health = bridge.health()
    assert health["success"] is True
    assert health["title"] == "Bridge"
    assert health["probes"]["read_ok"] is True
    assert health["probes"]["write_ok"] is True
    assert health["probes"]["bitable_ok"] is True
