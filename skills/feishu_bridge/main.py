"""Local FastAPI service for Feishu document bridge."""

from __future__ import annotations

import re

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from skills.feishu_bridge.bridge import FeishuBridgeError, build_bridge_from_env


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


app = FastAPI(title="Local Feishu Document Bridge", version="1.0.0")


def _map_error_status(message: str) -> int:
    # Prefer upstream HTTP status if present in bridge error text.
    match = re.search(r"status=(\d{3})", message)
    if match:
        return int(match.group(1))

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
    message = str(exc)
    return JSONResponse(
        status_code=_map_error_status(message),
        content={"success": False, "message": message},
    )


@app.post("/append_markdown")
def append_markdown(payload: AppendMarkdownRequest) -> dict:
    bridge = None
    try:
        bridge = build_bridge_from_env()
        return bridge.append_markdown(
            markdown=payload.markdown,
            section_title=payload.section_title,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)
    finally:
        if bridge is not None:
            bridge.close()


@app.post("/read_doc")
def read_doc(payload: ReadDocRequest) -> dict:
    bridge = None
    try:
        bridge = build_bridge_from_env()
        return bridge.read_doc(payload.format)
    except FeishuBridgeError as exc:
        return _error_response(exc)
    finally:
        if bridge is not None:
            bridge.close()


@app.post("/health")
def health() -> dict:
    bridge = None
    try:
        bridge = build_bridge_from_env()
        return bridge.health()
    except FeishuBridgeError as exc:
        return _error_response(exc)
    finally:
        if bridge is not None:
            bridge.close()


@app.post("/update_bitable")
def update_bitable(payload: UpdateBitableRequest) -> dict:
    bridge = None
    try:
        bridge = build_bridge_from_env()
        return bridge.update_bitable(
            app_token=payload.app_token,
            table_id=payload.table_id,
            record_id=payload.record_id,
            fields=payload.fields,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)
    finally:
        if bridge is not None:
            bridge.close()


@app.post("/create_sub_doc")
def create_sub_doc(payload: CreateSubDocRequest) -> dict:
    bridge = None
    try:
        bridge = build_bridge_from_env()
        return bridge.create_sub_doc(
            title=payload.title,
            folder_token=payload.folder_token,
        )
    except FeishuBridgeError as exc:
        return _error_response(exc)
    finally:
        if bridge is not None:
            bridge.close()
