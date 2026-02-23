"""Feishu document bridge core logic.

This module provides a local, reusable API client for reading and updating
one fixed Feishu doc. It is used by the skill CLI and FastAPI service.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

DEFAULT_BASE_URL = "https://open.feishu.cn"
DEFAULT_DOC_TOKEN = "H6ZfwwCcGiTMC2k5YgBcTBO3nKe"
_LOG_PATH = Path("logs/bridge.log")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_LOGGER = logging.getLogger("feishu_bridge")
if not _LOGGER.handlers:
    _LOGGER.setLevel(logging.INFO)
    _handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _LOGGER.addHandler(_handler)
    _LOGGER.propagate = False


class FeishuBridgeError(RuntimeError):
    """Raised when Feishu bridge operations fail."""


class FeishuAPIError(FeishuBridgeError):
    """Structured API error with status and provider metadata."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: int | None = None,
        log_id: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.log_id = log_id
        self.trace_id = trace_id
        parts = [message, f"status={status_code}"]
        if error_code is not None:
            parts.append(f"code={error_code}")
        if log_id:
            parts.append(f"log_id={log_id}")
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        super().__init__(" | ".join(parts))


def _extract_error_meta(resp: httpx.Response) -> tuple[str, str]:
    """Return (summary, log_id) from Feishu error payload if possible."""
    try:
        payload = resp.json()
        if isinstance(payload, dict):
            code = payload.get("code")
            msg = payload.get("msg") or payload.get("message") or ""
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            log_id = error.get("log_id") or payload.get("log_id") or ""
            summary = f"code={code} msg={msg}".strip()
            return summary, str(log_id) if log_id else ""
    except ValueError:
        pass
    return "", ""


@dataclass
class BridgeConfig:
    app_id: str
    app_secret: str
    document_id: str = DEFAULT_DOC_TOKEN
    base_url: str = DEFAULT_BASE_URL
    retry_count: int = 3
    retry_delay_seconds: float = 1.0

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        load_dotenv()
        app_id = os.getenv("FEISHU_APP_ID", "")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_id or not app_secret:
            raise FeishuBridgeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")
        return cls(
            app_id=app_id,
            app_secret=app_secret,
            document_id=os.getenv("FEISHU_DOC_TOKEN", DEFAULT_DOC_TOKEN),
            base_url=os.getenv("FEISHU_BASE_URL", DEFAULT_BASE_URL),
        )


class FeishuDocBridge:
    def __init__(self, config: BridgeConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=20.0)
        self._async_client = httpx.AsyncClient(timeout=20.0)
        self._tenant_access_token = ""
        self._token_expire_at = 0.0
        self._section_cache: dict[tuple[str, str], str] = {}

    def close(self) -> None:
        self._client.close()

    async def aclose(self) -> None:
        await self._async_client.aclose()
        self._client.close()

    def _doc_id(self, document_id: str | None = None) -> str:
        return (document_id or self.config.document_id).strip()

    def _needs_token_refresh(self) -> bool:
        return (not self._tenant_access_token) or (time.time() >= self._token_expire_at)

    def _refresh_tenant_token(self) -> None:
        url = f"{self.config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        resp = self._client.post(
            url,
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
        )
        data = self._decode_json(resp)
        if data.get("code") != 0:
            raise FeishuBridgeError(f"刷新 tenant_access_token 失败: {data}")

        token = data.get("tenant_access_token", "")
        expire = int(data.get("expire", 7200))
        if not token:
            raise FeishuBridgeError(f"tenant_access_token 缺失: {data}")

        self._tenant_access_token = token
        self._token_expire_at = time.time() + max(expire - 60, 60)

    async def _refresh_tenant_token_async(self) -> None:
        url = f"{self.config.base_url}/open-apis/auth/v3/tenant_access_token/internal"
        resp = await self._async_client.post(
            url,
            json={
                "app_id": self.config.app_id,
                "app_secret": self.config.app_secret,
            },
        )
        data = self._decode_json(resp)
        if data.get("code") != 0:
            raise FeishuBridgeError(f"刷新 tenant_access_token 失败: {data}")

        token = data.get("tenant_access_token", "")
        expire = int(data.get("expire", 7200))
        if not token:
            raise FeishuBridgeError(f"tenant_access_token 缺失: {data}")

        self._tenant_access_token = token
        self._token_expire_at = time.time() + max(expire - 60, 60)

    def _auth_headers(self) -> dict[str, str]:
        if self._needs_token_refresh():
            self._refresh_tenant_token()
        return {"Authorization": f"Bearer {self._tenant_access_token}"}

    async def _auth_headers_async(self) -> dict[str, str]:
        if self._needs_token_refresh():
            await self._refresh_tenant_token_async()
        return {"Authorization": f"Bearer {self._tenant_access_token}"}

    @staticmethod
    def _decode_json(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
        raise FeishuBridgeError(f"非法响应: status={resp.status_code} body={resp.text[:300]}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        refreshed = False
        trace_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()

        for attempt in range(1, self.config.retry_count + 1):
            resp = self._client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._auth_headers(),
            )
            _LOGGER.info(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "event": "feishu_request",
                        "attempt": attempt,
                        "method": method,
                        "path": path,
                        "status": resp.status_code,
                    },
                    ensure_ascii=False,
                )
            )

            if resp.status_code in {401, 403}:
                if refreshed:
                    summary, log_id = _extract_error_meta(resp)
                    error_code = None
                    try:
                        payload = resp.json()
                        if isinstance(payload, dict):
                            raw = payload.get("code")
                            if isinstance(raw, int):
                                error_code = raw
                    except ValueError:
                        pass
                    _LOGGER.error(
                        json.dumps(
                            {
                                "trace_id": trace_id,
                                "event": "auth_failed",
                                "path": path,
                                "status": resp.status_code,
                                "summary": summary,
                                "log_id": log_id,
                            },
                            ensure_ascii=False,
                        )
                    )
                    msg = f"鉴权失败: {resp.status_code}"
                    if summary:
                        msg = f"{msg} {summary}"
                    raise FeishuAPIError(
                        msg,
                        status_code=resp.status_code,
                        error_code=error_code,
                        log_id=log_id or None,
                        trace_id=trace_id,
                    )
                self._refresh_tenant_token()
                refreshed = True
                continue

            if resp.status_code == 429 and attempt < self.config.retry_count:
                time.sleep(self.config.retry_delay_seconds)
                continue

            data = self._decode_json(resp)
            # Feishu 业务错误码；同样触发率限重试。
            if data.get("code") in {99991663, 99991400} and attempt < self.config.retry_count:
                time.sleep(self.config.retry_delay_seconds)
                continue

            if data.get("code") != 0:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                log_id = ""
                if isinstance(data.get("error"), dict):
                    log_id = str(data.get("error", {}).get("log_id") or "")
                _LOGGER.error(
                    json.dumps(
                        {
                            "trace_id": trace_id,
                            "event": "feishu_error",
                            "path": path,
                            "status": resp.status_code,
                            "code": data.get("code"),
                            "msg": data.get("msg"),
                            "log_id": log_id,
                            "elapsed_ms": elapsed_ms,
                        },
                        ensure_ascii=False,
                    )
                )
                raise FeishuAPIError(
                    f"接口失败: path={path} msg={data.get('msg')}",
                    status_code=resp.status_code,
                    error_code=data.get("code") if isinstance(data.get("code"), int) else None,
                    log_id=log_id or None,
                    trace_id=trace_id,
                )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _LOGGER.info(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "event": "feishu_success",
                        "path": path,
                        "status": resp.status_code,
                        "elapsed_ms": elapsed_ms,
                    },
                    ensure_ascii=False,
                )
            )
            return data

        raise FeishuAPIError(
            f"请求重试耗尽: {path}",
            status_code=429,
            trace_id=trace_id,
        )

    async def _request_async(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.base_url}{path}"
        refreshed = False
        trace_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()

        for attempt in range(1, self.config.retry_count + 1):
            resp = await self._async_client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=await self._auth_headers_async(),
            )
            _LOGGER.info(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "event": "feishu_request",
                        "attempt": attempt,
                        "method": method,
                        "path": path,
                        "status": resp.status_code,
                    },
                    ensure_ascii=False,
                )
            )

            if resp.status_code in {401, 403}:
                if refreshed:
                    summary, log_id = _extract_error_meta(resp)
                    error_code = None
                    try:
                        payload = resp.json()
                        if isinstance(payload, dict):
                            raw = payload.get("code")
                            if isinstance(raw, int):
                                error_code = raw
                    except ValueError:
                        pass
                    msg = f"鉴权失败: {resp.status_code}"
                    if summary:
                        msg = f"{msg} {summary}"
                    raise FeishuAPIError(
                        msg,
                        status_code=resp.status_code,
                        error_code=error_code,
                        log_id=log_id or None,
                        trace_id=trace_id,
                    )
                await self._refresh_tenant_token_async()
                refreshed = True
                continue

            if resp.status_code == 429 and attempt < self.config.retry_count:
                time.sleep(self.config.retry_delay_seconds)
                continue

            data = self._decode_json(resp)
            if data.get("code") in {99991663, 99991400} and attempt < self.config.retry_count:
                time.sleep(self.config.retry_delay_seconds)
                continue

            if data.get("code") != 0:
                log_id = ""
                if isinstance(data.get("error"), dict):
                    log_id = str(data.get("error", {}).get("log_id") or "")
                raise FeishuAPIError(
                    f"接口失败: path={path} msg={data.get('msg')}",
                    status_code=resp.status_code,
                    error_code=data.get("code") if isinstance(data.get("code"), int) else None,
                    log_id=log_id or None,
                    trace_id=trace_id,
                )
            _LOGGER.info(
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "event": "feishu_success",
                        "path": path,
                        "status": resp.status_code,
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    },
                    ensure_ascii=False,
                )
            )
            return data

        raise FeishuAPIError(
            f"请求重试耗尽: {path}",
            status_code=429,
            trace_id=trace_id,
        )

    def get_document_meta(self, document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        return self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}",
        ).get("data", {})

    async def get_document_meta_async(self, document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        return (await self._request_async(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}",
        )).get("data", {})

    def health(self, document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        meta = self.get_document_meta(doc_id)
        title = meta.get("document", {}).get("title", "")
        probes = {"read_ok": True, "write_ok": False, "bitable_ok": False}
        try:
            diag = self.diagnose_permissions(document_id=doc_id)
            checks = diag.get("checks", {}) if isinstance(diag, dict) else {}
            probes["read_ok"] = bool(checks.get("doc_read_ok", False))
            probes["write_ok"] = bool(checks.get("doc_write_ok", False))
            # Bitable availability probe: permission/readability level.
            probes["bitable_ok"] = bool(checks.get("bitable_read_ok", False))
        except FeishuBridgeError:
            # Keep health endpoint resilient; top-level doc meta already proves service availability.
            pass
        return {
            "success": True,
            "document_id": doc_id,
            "title": title,
            "message": "service ok",
            "probes": probes,
        }

    async def health_async(self, document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        meta = await self.get_document_meta_async(doc_id)
        title = meta.get("document", {}).get("title", "")
        probes = {"read_ok": True, "write_ok": False, "bitable_ok": False}
        try:
            diag = await self.diagnose_permissions_async(document_id=doc_id)
            checks = diag.get("checks", {}) if isinstance(diag, dict) else {}
            probes["read_ok"] = bool(checks.get("doc_read_ok", False))
            probes["write_ok"] = bool(checks.get("doc_write_ok", False))
            probes["bitable_ok"] = bool(checks.get("bitable_read_ok", False))
        except FeishuBridgeError:
            pass
        return {
            "success": True,
            "document_id": doc_id,
            "title": title,
            "message": "service ok",
            "probes": probes,
        }

    def read_doc(self, format_type: str = "markdown", document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        fmt = (format_type or "markdown").lower()
        if fmt == "markdown":
            raw = self._request(
                "GET",
                f"/open-apis/docx/v1/documents/{doc_id}/raw_content",
            )
            return {
                "success": True,
                "format": "markdown",
                "content": raw.get("data", {}).get("content", ""),
            }

        content = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}/content",
            params={"page_size": 500},
        )
        return {
            "success": True,
            "format": "raw",
            "content": content.get("data", {}),
        }

    async def read_doc_async(self, format_type: str = "markdown", document_id: str | None = None) -> dict[str, Any]:
        doc_id = self._doc_id(document_id)
        fmt = (format_type or "markdown").lower()
        if fmt == "markdown":
            raw = await self._request_async(
                "GET",
                f"/open-apis/docx/v1/documents/{doc_id}/raw_content",
            )
            return {
                "success": True,
                "format": "markdown",
                "content": raw.get("data", {}).get("content", ""),
            }
        content = await self._request_async(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}/content",
            params={"page_size": 500},
        )
        return {
            "success": True,
            "format": "raw",
            "content": content.get("data", {}),
        }

    def _list_blocks(self, document_id: str | None = None) -> list[dict[str, Any]]:
        doc_id = self._doc_id(document_id)
        data = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}/blocks",
            params={"page_size": 500},
        ).get("data", {})

        if isinstance(data.get("items"), list):
            return data.get("items", [])
        if isinstance(data.get("children"), list):
            return data.get("children", [])
        # 部分响应会用 block_map。
        if isinstance(data.get("block_map"), dict):
            return list(data["block_map"].values())
        return []

    async def _list_blocks_async(self, document_id: str | None = None) -> list[dict[str, Any]]:
        doc_id = self._doc_id(document_id)
        data = (await self._request_async(
            "GET",
            f"/open-apis/docx/v1/documents/{doc_id}/blocks",
            params={"page_size": 500},
        )).get("data", {})
        if isinstance(data.get("items"), list):
            return data.get("items", [])
        if isinstance(data.get("children"), list):
            return data.get("children", [])
        if isinstance(data.get("block_map"), dict):
            return list(data["block_map"].values())
        return []

    def _get_root_block_id(self, document_id: str | None = None) -> str:
        doc_id = self._doc_id(document_id)
        blocks = self._list_blocks(doc_id)
        if not blocks:
            raise FeishuBridgeError("文档块为空，无法定位根块")

        for block in blocks:
            parent_id = block.get("parent_id")
            block_type = block.get("block_type")
            block_id = block.get("block_id") or block.get("id")
            if block_id and (parent_id in (None, "", doc_id)) and block_type == 1:
                return str(block_id)

        # 回退：取第一个可用 block_id，避免因字段差异导致全失败。
        for block in blocks:
            block_id = block.get("block_id") or block.get("id")
            if block_id:
                return str(block_id)
        raise FeishuBridgeError("无法解析文档根块 ID")

    async def _get_root_block_id_async(self, document_id: str | None = None) -> str:
        doc_id = self._doc_id(document_id)
        blocks = await self._list_blocks_async(doc_id)
        if not blocks:
            raise FeishuBridgeError("文档块为空，无法定位根块")
        for block in blocks:
            parent_id = block.get("parent_id")
            block_type = block.get("block_type")
            block_id = block.get("block_id") or block.get("id")
            if block_id and (parent_id in (None, "", doc_id)) and block_type == 1:
                return str(block_id)
        for block in blocks:
            block_id = block.get("block_id") or block.get("id")
            if block_id:
                return str(block_id)
        raise FeishuBridgeError("无法解析文档根块 ID")

    @staticmethod
    def _extract_block_text(block: dict[str, Any]) -> str:
        text_elements = (
            block.get("text", {}).get("elements")
            or block.get("heading1", {}).get("elements")
            or block.get("heading2", {}).get("elements")
            or block.get("heading3", {}).get("elements")
            or []
        )
        chunks: list[str] = []
        for element in text_elements:
            text_run = element.get("text_run", {})
            content = text_run.get("content")
            if content:
                chunks.append(content)
        return "".join(chunks).strip()

    @staticmethod
    def _normalize_section_title(text: str) -> str:
        s = (text or "").strip()
        # Drop common heading prefixes like "4. " / "3) " / "第4节 ".
        s = re.sub(r"^(第\s*\d+\s*[章节部分]|[0-9]+[\.\)\-、])\s*", "", s)
        s = re.sub(r"\s+", "", s)
        return s.lower()

    def _find_section_block_id(self, section_title: str, document_id: str | None = None) -> str | None:
        if not section_title:
            return None

        doc_id = self._doc_id(document_id)
        target = section_title.strip()
        normalized_target = self._normalize_section_title(target)
        cache_key = (doc_id, normalized_target)
        if cache_key in self._section_cache:
            return self._section_cache[cache_key]

        for block in self._list_blocks(doc_id):
            text = self._extract_block_text(block)
            if text == target or self._normalize_section_title(text) == normalized_target:
                block_id = block.get("block_id") or block.get("id")
                if block_id:
                    block_id_str = str(block_id)
                    self._section_cache[cache_key] = block_id_str
                    return block_id_str
        return None

    async def _find_section_block_id_async(
        self,
        section_title: str,
        document_id: str | None = None,
    ) -> str | None:
        if not section_title:
            return None

        doc_id = self._doc_id(document_id)
        target = section_title.strip()
        normalized_target = self._normalize_section_title(target)
        cache_key = (doc_id, normalized_target)
        if cache_key in self._section_cache:
            return self._section_cache[cache_key]

        for block in await self._list_blocks_async(doc_id):
            text = self._extract_block_text(block)
            if text == target or self._normalize_section_title(text) == normalized_target:
                block_id = block.get("block_id") or block.get("id")
                if block_id:
                    block_id_str = str(block_id)
                    self._section_cache[cache_key] = block_id_str
                    return block_id_str
        return None

    def _convert_markdown_to_blocks(self, markdown: str, document_id: str | None = None) -> list[dict[str, Any]]:
        doc_id = self._doc_id(document_id)
        payloads = [
            {
                "document_id": doc_id,
                "from": "markdown",
                "to": "block",
                "content": markdown,
            },
            {
                "from": "markdown",
                "to": "docx_block",
                "content": markdown,
            },
        ]
        last_error: Exception | None = None

        for payload in payloads:
            try:
                data = self._request(
                    "POST",
                    "/open-apis/docx/v1/documents/convert",
                    json_body=payload,
                ).get("data", {})
                blocks = data.get("blocks") or data.get("children") or []
                if isinstance(blocks, list) and blocks:
                    return blocks
            except Exception as exc:  # pragma: no cover - failover path
                last_error = exc

        # Fallback: plain text paragraph blocks per line.
        lines = [line for line in markdown.splitlines() if line.strip()]
        if not lines and markdown.strip():
            lines = [markdown.strip()]
        if not lines:
            raise FeishuBridgeError("markdown 为空，无法追加")

        fallback_blocks: list[dict[str, Any]] = []
        for line in lines:
            fallback_blocks.append(
                {
                    "block_type": 2,
                    "text": {
                        "elements": [
                            {
                                "text_run": {"content": line},
                            }
                        ]
                    },
                }
            )

        if last_error:
            # 保留 fallback 行为，不中断流程。
            _ = last_error
        return fallback_blocks

    async def _convert_markdown_to_blocks_async(
        self,
        markdown: str,
        document_id: str | None = None,
    ) -> list[dict[str, Any]]:
        doc_id = self._doc_id(document_id)
        payloads = [
            {
                "document_id": doc_id,
                "from": "markdown",
                "to": "block",
                "content": markdown,
            },
            {
                "from": "markdown",
                "to": "docx_block",
                "content": markdown,
            },
        ]
        for payload in payloads:
            try:
                data = (await self._request_async(
                    "POST",
                    "/open-apis/docx/v1/documents/convert",
                    json_body=payload,
                )).get("data", {})
                blocks = data.get("blocks") or data.get("children") or []
                if isinstance(blocks, list) and blocks:
                    return blocks
            except Exception:
                continue
        return self._convert_markdown_to_blocks(markdown, doc_id)

    def append_markdown(
        self,
        markdown: str,
        section_title: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        if not markdown or not markdown.strip():
            raise FeishuBridgeError("markdown 不能为空")
        doc_id = self._doc_id(document_id)

        parent_block_id = self._find_section_block_id(section_title or "", doc_id)
        if not parent_block_id:
            if section_title and section_title.strip():
                raise FeishuBridgeError(f"section 不存在: {section_title}")
            parent_block_id = self._get_root_block_id(doc_id)

        blocks = self._convert_markdown_to_blocks(markdown, doc_id)
        resp = self._request(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_id}/blocks/{parent_block_id}/children",
            json_body={"children": blocks},
        )

        block_id = ""
        data = resp.get("data", {})
        children = data.get("children") or data.get("items") or []
        if children and isinstance(children[0], dict):
            block_id = children[0].get("block_id") or children[0].get("id") or ""

        return {
            "success": True,
            "block_id": block_id,
            "message": "已追加",
            "parent_block_id": parent_block_id,
            "count": len(blocks),
        }

    async def append_markdown_async(
        self,
        markdown: str,
        section_title: str | None = None,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        if not markdown or not markdown.strip():
            raise FeishuBridgeError("markdown 不能为空")
        doc_id = self._doc_id(document_id)

        parent_block_id = await self._find_section_block_id_async(section_title or "", doc_id)
        if not parent_block_id:
            if section_title and section_title.strip():
                raise FeishuBridgeError(f"section 不存在: {section_title}")
            parent_block_id = await self._get_root_block_id_async(doc_id)

        blocks = await self._convert_markdown_to_blocks_async(markdown, doc_id)
        resp = await self._request_async(
            "POST",
            f"/open-apis/docx/v1/documents/{doc_id}/blocks/{parent_block_id}/children",
            json_body={"children": blocks},
        )

        block_id = ""
        data = resp.get("data", {})
        children = data.get("children") or data.get("items") or []
        if children and isinstance(children[0], dict):
            block_id = children[0].get("block_id") or children[0].get("id") or ""

        return {
            "success": True,
            "block_id": block_id,
            "message": "已追加",
            "parent_block_id": parent_block_id,
            "count": len(blocks),
        }

    def update_bitable(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        if not app_token.strip():
            raise FeishuBridgeError("app_token 不能为空")
        if not table_id.strip():
            raise FeishuBridgeError("table_id 不能为空")
        if not record_id.strip():
            raise FeishuBridgeError("record_id 不能为空")
        if not isinstance(fields, dict) or not fields:
            raise FeishuBridgeError("fields 不能为空且必须是对象")

        # 优先 PATCH，部分租户仅支持 PUT 时自动回退。
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        payload = {"fields": fields}
        try:
            resp = self._request("PATCH", path, json_body=payload)
        except FeishuBridgeError as exc:
            msg = str(exc).lower()
            allow_fallback = ("1254003" in msg) or ("method not allowed" in msg)
            if not allow_fallback:
                raise
            resp = self._request("PUT", path, json_body=payload)

        data = resp.get("data", {})
        record = data.get("record", {}) if isinstance(data, dict) else {}
        return {
            "success": True,
            "message": "已更新",
            "app_token": app_token,
            "table_id": table_id,
            "record_id": record_id,
            "record": record,
        }

    async def update_bitable_async(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        if not app_token.strip():
            raise FeishuBridgeError("app_token 不能为空")
        if not table_id.strip():
            raise FeishuBridgeError("table_id 不能为空")
        if not record_id.strip():
            raise FeishuBridgeError("record_id 不能为空")
        if not isinstance(fields, dict) or not fields:
            raise FeishuBridgeError("fields 不能为空且必须是对象")
        path = f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        payload = {"fields": fields}
        try:
            resp = await self._request_async("PATCH", path, json_body=payload)
        except FeishuBridgeError as exc:
            msg = str(exc).lower()
            if ("1254003" not in msg) and ("method not allowed" not in msg):
                raise
            resp = await self._request_async("PUT", path, json_body=payload)
        data = resp.get("data", {})
        record = data.get("record", {}) if isinstance(data, dict) else {}
        return {
            "success": True,
            "message": "已更新",
            "app_token": app_token,
            "table_id": table_id,
            "record_id": record_id,
            "record": record,
        }

    def create_sub_doc(self, title: str, folder_token: str | None = None) -> dict[str, Any]:
        if not title or not title.strip():
            raise FeishuBridgeError("title 不能为空")

        payload: dict[str, Any] = {"title": title.strip()}
        if folder_token and folder_token.strip():
            payload["folder_token"] = folder_token.strip()

        resp = self._request(
            "POST",
            "/open-apis/docx/v1/documents",
            json_body=payload,
        )
        data = resp.get("data", {})
        document = data.get("document", {}) if isinstance(data, dict) else {}

        document_id = (
            document.get("document_id")
            or data.get("document_id")
            or document.get("token")
            or data.get("token")
            or ""
        )
        if not document_id:
            raise FeishuBridgeError(f"创建子文档成功但未返回 document_id: {data}")

        url = (
            document.get("url")
            or data.get("url")
            or f"https://{self.config.base_url.removeprefix('https://')}/docx/{document_id}"
        )
        return {
            "success": True,
            "message": "已创建",
            "title": title.strip(),
            "document_id": document_id,
            "url": url,
        }

    async def create_sub_doc_async(self, title: str, folder_token: str | None = None) -> dict[str, Any]:
        if not title or not title.strip():
            raise FeishuBridgeError("title 不能为空")
        payload: dict[str, Any] = {"title": title.strip()}
        if folder_token and folder_token.strip():
            payload["folder_token"] = folder_token.strip()
        resp = await self._request_async(
            "POST",
            "/open-apis/docx/v1/documents",
            json_body=payload,
        )
        data = resp.get("data", {})
        document = data.get("document", {}) if isinstance(data, dict) else {}
        document_id = (
            document.get("document_id")
            or data.get("document_id")
            or document.get("token")
            or data.get("token")
            or ""
        )
        if not document_id:
            raise FeishuBridgeError(f"创建子文档成功但未返回 document_id: {data}")
        url = (
            document.get("url")
            or data.get("url")
            or f"https://{self.config.base_url.removeprefix('https://')}/docx/{document_id}"
        )
        return {
            "success": True,
            "message": "已创建",
            "title": title.strip(),
            "document_id": document_id,
            "url": url,
        }

    def _resolve_bitable_from_doc(self, document_id: str) -> tuple[str, str] | None:
        data = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{document_id}/blocks",
            params={"page_size": 500},
        ).get("data", {})
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        for block in items:
            if block.get("block_type") != 53:
                continue
            ref = block.get("reference_base") if isinstance(block.get("reference_base"), dict) else {}
            token = str(ref.get("token") or "")
            if "_tbl" in token:
                split_at = token.find("_tbl")
                app_token = token[:split_at]
                table_id = token[split_at + 1 :]
                if app_token and table_id:
                    return app_token, table_id
        return None

    async def _resolve_bitable_from_doc_async(self, document_id: str) -> tuple[str, str] | None:
        data = (await self._request_async(
            "GET",
            f"/open-apis/docx/v1/documents/{document_id}/blocks",
            params={"page_size": 500},
        )).get("data", {})
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        for block in items:
            if block.get("block_type") != 53:
                continue
            ref = block.get("reference_base") if isinstance(block.get("reference_base"), dict) else {}
            token = str(ref.get("token") or "")
            if "_tbl" in token:
                split_at = token.find("_tbl")
                app_token = token[:split_at]
                table_id = token[split_at + 1 :]
                if app_token and table_id:
                    return app_token, table_id
        return None

    def _get_root_children_snapshot(self, document_id: str) -> tuple[str, list[str], dict[str, dict[str, Any]]]:
        data = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{document_id}/blocks",
            params={"page_size": 500},
        ).get("data", {})
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        by_id: dict[str, dict[str, Any]] = {}
        for b in items:
            bid = b.get("block_id") or b.get("id")
            if bid:
                by_id[str(bid)] = b

        root_id = ""
        children: list[str] = []
        for b in items:
            if b.get("block_type") == 1:
                bid = b.get("block_id") or b.get("id")
                if bid:
                    root_id = str(bid)
                    children = [str(x) for x in (b.get("children") or []) if x]
                    break
        if not root_id:
            raise FeishuBridgeError("未找到文档根块，无法清理章节")
        return root_id, children, by_id

    def diagnose_permissions(
        self,
        *,
        document_id: str | None = None,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> dict[str, Any]:
        target_doc = (document_id or self.config.document_id).strip()
        checks: dict[str, Any] = {
            "doc_read_ok": False,
            "doc_write_ok": False,
            "bitable_read_ok": False,
            "bitable_write_ok": False,
        }
        errors: dict[str, str] = {}

        try:
            self._request("GET", f"/open-apis/docx/v1/documents/{target_doc}")
            checks["doc_read_ok"] = True
        except FeishuBridgeError as exc:
            errors["doc_read_error"] = str(exc)

        # Write capability probe without mutating content: docx convert endpoint.
        try:
            self._request(
                "POST",
                "/open-apis/docx/v1/documents/convert",
                json_body={
                    "document_id": target_doc,
                    "from": "markdown",
                    "to": "block",
                    "content": "permission probe",
                },
            )
            checks["doc_write_ok"] = True
        except FeishuBridgeError as exc:
            errors["doc_write_error"] = str(exc)

        resolved = None
        if app_token and table_id:
            resolved = (app_token.strip(), table_id.strip())
        else:
            try:
                resolved = self._resolve_bitable_from_doc(target_doc)
            except FeishuBridgeError as exc:
                errors["bitable_resolve_error"] = str(exc)

        if resolved:
            app, tbl = resolved
            try:
                recs = self._request(
                    "GET",
                    f"/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
                    params={"page_size": 1},
                ).get("data", {})
                checks["bitable_read_ok"] = True
                first = (recs.get("items") or [None])[0]
                if first and isinstance(first, dict) and first.get("record_id"):
                    record_id = str(first["record_id"])
                    fields = first.get("fields") if isinstance(first.get("fields"), dict) else {}
                    # Best-effort write probe: no-op update using existing fields.
                    probe_fields = fields if fields else {"_probe": "noop"}
                    self.update_bitable(app, tbl, record_id, probe_fields)
                    checks["bitable_write_ok"] = True
                else:
                    errors["bitable_write_error"] = "bitable 无记录，跳过写权限探测"
            except FeishuBridgeError as exc:
                msg = str(exc)
                if not checks["bitable_read_ok"]:
                    errors["bitable_read_error"] = msg
                else:
                    errors["bitable_write_error"] = msg
        else:
            errors["bitable_target_error"] = "未提供 app_token/table_id，且文档中未解析到多维表格"

        return {
            "success": True,
            "document_id": target_doc,
            "bitable_target": {"app_token": resolved[0], "table_id": resolved[1]} if resolved else None,
            "checks": checks,
            "errors": errors,
        }

    async def diagnose_permissions_async(
        self,
        *,
        document_id: str | None = None,
        app_token: str | None = None,
        table_id: str | None = None,
    ) -> dict[str, Any]:
        # Keep output parity with sync method while using async request path.
        target_doc = (document_id or self.config.document_id).strip()
        checks: dict[str, Any] = {
            "doc_read_ok": False,
            "doc_write_ok": False,
            "bitable_read_ok": False,
            "bitable_write_ok": False,
        }
        errors: dict[str, str] = {}
        try:
            await self._request_async("GET", f"/open-apis/docx/v1/documents/{target_doc}")
            checks["doc_read_ok"] = True
        except FeishuBridgeError as exc:
            errors["doc_read_error"] = str(exc)
        try:
            await self._request_async(
                "POST",
                "/open-apis/docx/v1/documents/convert",
                json_body={
                    "document_id": target_doc,
                    "from": "markdown",
                    "to": "block",
                    "content": "permission probe",
                },
            )
            checks["doc_write_ok"] = True
        except FeishuBridgeError as exc:
            errors["doc_write_error"] = str(exc)

        resolved = None
        if app_token and table_id:
            resolved = (app_token.strip(), table_id.strip())
        else:
            try:
                resolved = self._resolve_bitable_from_doc(target_doc)
            except FeishuBridgeError as exc:
                errors["bitable_resolve_error"] = str(exc)
        if resolved:
            app, tbl = resolved
            try:
                recs = (await self._request_async(
                    "GET",
                    f"/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
                    params={"page_size": 1},
                )).get("data", {})
                checks["bitable_read_ok"] = True
                first = (recs.get("items") or [None])[0]
                if first and isinstance(first, dict) and first.get("record_id"):
                    record_id = str(first["record_id"])
                    fields = first.get("fields") if isinstance(first.get("fields"), dict) else {}
                    probe_fields = fields if fields else {"_probe": "noop"}
                    await self.update_bitable_async(app, tbl, record_id, probe_fields)
                    checks["bitable_write_ok"] = True
                else:
                    errors["bitable_write_error"] = "bitable 无记录，跳过写权限探测"
            except FeishuBridgeError as exc:
                msg = str(exc)
                if not checks["bitable_read_ok"]:
                    errors["bitable_read_error"] = msg
                else:
                    errors["bitable_write_error"] = msg
        else:
            errors["bitable_target_error"] = "未提供 app_token/table_id，且文档中未解析到多维表格"
        return {
            "success": True,
            "document_id": target_doc,
            "bitable_target": {"app_token": resolved[0], "table_id": resolved[1]} if resolved else None,
            "checks": checks,
            "errors": errors,
        }

    def clear_section(self, section_title: str, document_id: str | None = None) -> dict[str, Any]:
        if not section_title or not section_title.strip():
            raise FeishuBridgeError("section_title 不能为空")
        doc_id = self._doc_id(document_id)
        section_id = self._find_section_block_id(section_title, doc_id)
        if not section_id:
            raise FeishuBridgeError(f"section 不存在: {section_title}")

        root_id, children, by_id = self._get_root_children_snapshot(doc_id)
        if section_id not in children:
            raise FeishuBridgeError(f"section 不在根级块列表中: {section_title}")

        start = children.index(section_id) + 1
        end = len(children)
        for i in range(start, len(children)):
            bid = children[i]
            block = by_id.get(bid, {})
            # Heading block marks next section boundary.
            if block.get("block_type") == 4:
                end = i
                break

        if start >= end:
            return {
                "success": True,
                "message": "章节已为空",
                "document_id": doc_id,
                "section_title": section_title,
                "deleted_count": 0,
            }

        self._request(
            "DELETE",
            f"/open-apis/docx/v1/documents/{doc_id}/blocks/{root_id}/children/batch_delete",
            json_body={"start_index": start, "end_index": end},
        )
        return {
            "success": True,
            "message": "章节已清空",
            "document_id": doc_id,
            "section_title": section_title,
            "deleted_count": end - start,
        }

    def replace_section(
        self,
        section_title: str,
        markdown: str,
        document_id: str | None = None,
    ) -> dict[str, Any]:
        clear = self.clear_section(section_title, document_id=document_id)
        append = self.append_markdown(markdown, section_title=section_title, document_id=document_id)
        return {
            "success": True,
            "message": "章节已替换",
            "document_id": self._doc_id(document_id),
            "section_title": section_title,
            "cleared": clear.get("deleted_count", 0),
            "block_id": append.get("block_id", ""),
            "count": append.get("count", 0),
        }

    @staticmethod
    def _to_unix_ms(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            raw = value.strip()
            if raw.isdigit():
                return int(raw)
            for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                    return int(dt.timestamp() * 1000)
                except ValueError:
                    continue
        return None

    def adapt_bitable_fields(
        self,
        app_token: str,
        table_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        schema = self._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            params={"page_size": 500},
        ).get("data", {})
        items = schema.get("items", []) if isinstance(schema.get("items"), list) else []
        by_name = {x.get("field_name"): x for x in items}
        adapted: dict[str, Any] = {}
        for key, value in fields.items():
            meta = by_name.get(key, {})
            ftype = meta.get("type")
            if ftype == 5:
                ms = self._to_unix_ms(value)
                adapted[key] = ms if ms is not None else value
                continue
            if ftype == 21:
                if isinstance(value, str):
                    adapted[key] = [value]
                else:
                    adapted[key] = value
                continue
            if ftype == 3 and isinstance(value, str):
                # Keep option display name if provided; table config maps it.
                adapted[key] = value
                continue
            adapted[key] = value
        return adapted

    def batch_upsert_tasks(
        self,
        app_token: str,
        table_id: str,
        tasks: list[dict[str, Any]],
        key_field: str = "任务",
    ) -> dict[str, Any]:
        if not tasks:
            raise FeishuBridgeError("tasks 不能为空")
        existing = self._request(
            "GET",
            f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            params={"page_size": 500},
        ).get("data", {})
        items = existing.get("items", []) if isinstance(existing.get("items"), list) else []
        key_to_record: dict[str, str] = {}
        for row in items:
            rid = row.get("record_id")
            val = (row.get("fields") or {}).get(key_field)
            if rid and isinstance(val, str) and val.strip():
                key_to_record[val.strip()] = str(rid)

        created = 0
        updated = 0
        for raw in tasks:
            if not isinstance(raw, dict):
                continue
            fields = raw.get("fields") if isinstance(raw.get("fields"), dict) else raw
            if not isinstance(fields, dict):
                continue
            key = fields.get(key_field)
            if not isinstance(key, str) or not key.strip():
                raise FeishuBridgeError(f"task 缺少关键字段: {key_field}")
            adapted = self.adapt_bitable_fields(app_token, table_id, fields)
            if key.strip() in key_to_record:
                self.update_bitable(app_token, table_id, key_to_record[key.strip()], adapted)
                updated += 1
            else:
                self._request(
                    "POST",
                    f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                    json_body={"fields": adapted},
                )
                created += 1
        return {
            "success": True,
            "message": "批量 upsert 完成",
            "created": created,
            "updated": updated,
            "total": created + updated,
        }


def build_bridge_from_env() -> FeishuDocBridge:
    return FeishuDocBridge(BridgeConfig.from_env())
