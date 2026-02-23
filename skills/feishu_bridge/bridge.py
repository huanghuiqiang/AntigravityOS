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
        self._tenant_access_token = ""
        self._token_expire_at = 0.0

    def close(self) -> None:
        self._client.close()

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

    def _auth_headers(self) -> dict[str, str]:
        if self._needs_token_refresh():
            self._refresh_tenant_token()
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
                    parts = [f"鉴权失败: {resp.status_code}"]
                    if summary:
                        parts.append(summary)
                    if log_id:
                        parts.append(f"log_id={log_id}")
                    parts.append(f"trace_id={trace_id}")
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
                    raise FeishuBridgeError(" | ".join(parts))
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
                raise FeishuBridgeError(
                    f"接口失败: path={path} status={resp.status_code} payload={data} trace_id={trace_id}"
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

        raise FeishuBridgeError(f"请求重试耗尽: {path} trace_id={trace_id}")

    def get_document_meta(self) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{self.config.document_id}",
        ).get("data", {})

    def health(self) -> dict[str, Any]:
        meta = self.get_document_meta()
        title = meta.get("document", {}).get("title", "")
        return {
            "success": True,
            "document_id": self.config.document_id,
            "title": title,
            "message": "service ok",
        }

    def read_doc(self, format_type: str = "markdown") -> dict[str, Any]:
        fmt = (format_type or "markdown").lower()
        if fmt == "markdown":
            raw = self._request(
                "GET",
                f"/open-apis/docx/v1/documents/{self.config.document_id}/raw_content",
            )
            return {
                "success": True,
                "format": "markdown",
                "content": raw.get("data", {}).get("content", ""),
            }

        content = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{self.config.document_id}/content",
            params={"page_size": 500},
        )
        return {
            "success": True,
            "format": "raw",
            "content": content.get("data", {}),
        }

    def _list_blocks(self) -> list[dict[str, Any]]:
        data = self._request(
            "GET",
            f"/open-apis/docx/v1/documents/{self.config.document_id}/blocks",
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

    def _get_root_block_id(self) -> str:
        blocks = self._list_blocks()
        if not blocks:
            raise FeishuBridgeError("文档块为空，无法定位根块")

        for block in blocks:
            parent_id = block.get("parent_id")
            block_type = block.get("block_type")
            block_id = block.get("block_id") or block.get("id")
            if block_id and (parent_id in (None, "", self.config.document_id)) and block_type == 1:
                return str(block_id)

        # 回退：取第一个可用 block_id，避免因字段差异导致全失败。
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

    def _find_section_block_id(self, section_title: str) -> str | None:
        if not section_title:
            return None

        target = section_title.strip()
        normalized_target = self._normalize_section_title(target)
        for block in self._list_blocks():
            text = self._extract_block_text(block)
            if text == target or self._normalize_section_title(text) == normalized_target:
                block_id = block.get("block_id") or block.get("id")
                if block_id:
                    return str(block_id)
        return None

    def _convert_markdown_to_blocks(self, markdown: str) -> list[dict[str, Any]]:
        payloads = [
            {
                "document_id": self.config.document_id,
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

    def append_markdown(self, markdown: str, section_title: str | None = None) -> dict[str, Any]:
        if not markdown or not markdown.strip():
            raise FeishuBridgeError("markdown 不能为空")

        parent_block_id = self._find_section_block_id(section_title or "")
        if not parent_block_id:
            if section_title and section_title.strip():
                raise FeishuBridgeError(f"section 不存在: {section_title}")
            parent_block_id = self._get_root_block_id()

        blocks = self._convert_markdown_to_blocks(markdown)
        resp = self._request(
            "POST",
            f"/open-apis/docx/v1/documents/{self.config.document_id}/blocks/{parent_block_id}/children",
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
                app_token, table_id = token.split("_", 1)
                if app_token and table_id:
                    return app_token, table_id
        return None

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


def build_bridge_from_env() -> FeishuDocBridge:
    return FeishuDocBridge(BridgeConfig.from_env())
