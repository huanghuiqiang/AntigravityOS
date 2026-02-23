"""Local FastAPI service for Feishu document bridge."""

from __future__ import annotations

import inspect
from threading import Lock

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from skills.feishu_bridge.bridge import FeishuAPIError, FeishuBridgeError, build_bridge_from_env


class AppendMarkdownRequest(BaseModel):
    markdown: str
    section_title: str | None = None


class ReadDocRequest(BaseModel):
    format: str = "markdown"


class UpdateBitableRequest(BaseModel):
    app_token: str
    table_id: str
    record_id: str
    fields: dict


class CreateSubDocRequest(BaseModel):
    title: str
    folder_token: str | None = None


class DiagnosePermissionsRequest(BaseModel):
    document_id: str | None = None
    app_token: str | None = None
    table_id: str | None = None


app = FastAPI(title="Local Feishu Document Bridge", version="1.0.0")
_bridge_lock = Lock()
_bridge_singleton = None


def _get_bridge():
    global _bridge_singleton
    if _bridge_singleton is not None:
        return _bridge_singleton
    with _bridge_lock:
        if _bridge_singleton is None:
            _bridge_singleton = build_bridge_from_env()
    return _bridge_singleton


@app.on_event("shutdown")
async def _shutdown_bridge() -> None:
    global _bridge_singleton
    with _bridge_lock:
        bridge = _bridge_singleton
        _bridge_singleton = None
    if bridge is not None:
        aclose = getattr(bridge, "aclose", None)
        if callable(aclose):
            result = aclose()
            if inspect.isawaitable(result):
                await result
        else:
            bridge.close()


def _map_error_status(message: str) -> int:
    # Legacy fallback for non-structured exceptions.
    if "鉴权失败: 401" in message:
        return 401
    if "鉴权失败: 403" in message:
        return 403
    if "请求重试耗尽" in message:
        return 429
    if "不能为空" in message or "格式" in message:
        return 400
    if "未配置" in message:
        return 500
    if "非法响应" in message:
        return 502
    return 500


def _error_response(exc: FeishuBridgeError) -> JSONResponse:
    if isinstance(exc, FeishuAPIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.message,
                "error_code": exc.error_code,
                "log_id": exc.log_id,
                "trace_id": exc.trace_id,
            },
        )

    message = str(exc)
    return JSONResponse(
        status_code=_map_error_status(message),
        content={"success": False, "message": message},
    )


async def _call_bridge(bridge, async_name: str, sync_name: str, **kwargs):
    fn = getattr(bridge, async_name, None)
    if fn is None:
        fn = getattr(bridge, sync_name)
    result = fn(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


@app.post("/append_markdown")
async def append_markdown(payload: AppendMarkdownRequest) -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(
            bridge,
            "append_markdown_async",
            "append_markdown",
            markdown=payload.markdown,
            section_title=payload.section_title,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)


@app.post("/read_doc")
async def read_doc(payload: ReadDocRequest) -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(
            bridge,
            "read_doc_async",
            "read_doc",
            format_type=payload.format,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)


@app.post("/health")
async def health() -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(bridge, "health_async", "health")
    except FeishuBridgeError as exc:
        return _error_response(exc)


@app.post("/update_bitable")
async def update_bitable(payload: UpdateBitableRequest) -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(
            bridge,
            "update_bitable_async",
            "update_bitable",
            app_token=payload.app_token,
            table_id=payload.table_id,
            record_id=payload.record_id,
            fields=payload.fields,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)


@app.post("/create_sub_doc")
async def create_sub_doc(payload: CreateSubDocRequest) -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(
            bridge,
            "create_sub_doc_async",
            "create_sub_doc",
            title=payload.title,
            folder_token=payload.folder_token,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)


@app.post("/diagnose_permissions")
async def diagnose_permissions(payload: DiagnosePermissionsRequest) -> dict:
    try:
        bridge = _get_bridge()
        return await _call_bridge(
            bridge,
            "diagnose_permissions_async",
            "diagnose_permissions",
            document_id=payload.document_id,
            app_token=payload.app_token,
            table_id=payload.table_id,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)
