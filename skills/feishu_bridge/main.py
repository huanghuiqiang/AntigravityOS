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


app = FastAPI(title="Local Feishu Document Bridge", version="1.0.0")


@app.post("/append_markdown")
def append_markdown(payload: AppendMarkdownRequest) -> dict:
    bridge = build_bridge_from_env()
    try:
        return bridge.append_markdown(
            markdown=payload.markdown,
            section_title=payload.section_title,
        )
    except FeishuBridgeError as exc:
        return {"success": False, "message": str(exc)}
    finally:
        bridge.close()


@app.post("/read_doc")
def read_doc(payload: ReadDocRequest) -> dict:
    bridge = build_bridge_from_env()
    try:
        return bridge.read_doc(payload.format)
    except FeishuBridgeError as exc:
        return {"success": False, "message": str(exc)}
    finally:
        bridge.close()


@app.post("/health")
def health() -> dict:
    bridge = build_bridge_from_env()
    try:
        return bridge.health()
    except FeishuBridgeError as exc:
        return {"success": False, "message": str(exc)}
    finally:
        bridge.close()
