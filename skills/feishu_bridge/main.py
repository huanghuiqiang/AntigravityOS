"""Local FastAPI service for Feishu document bridge."""

from __future__ import annotations

from fastapi import FastAPI
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


app = FastAPI(title="Local Feishu Document Bridge", version="1.0.0")


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
        return {"success": False, "message": str(exc)}
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
        return {"success": False, "message": str(exc)}
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
        return {"success": False, "message": str(exc)}
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
        return {"success": False, "message": str(exc)}
    finally:
        if bridge is not None:
            bridge.close()
