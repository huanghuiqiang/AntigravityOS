"""Audit logging for tool gateway."""

from __future__ import annotations

import json
import logging
from pathlib import Path

_LOGGER_NAME = "tool_gateway.audit"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "tool_gateway.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def audit_event(
    *,
    trace_id: str,
    tool_name: str,
    actor: str,
    result: str,
    external_id: str | None = None,
    input_hash: str | None = None,
) -> None:
    payload = {
        "trace_id": trace_id,
        "tool_name": tool_name,
        "actor": actor,
        "result": result,
        "external_id": external_id,
        "input_hash": input_hash,
    }
    logger = _build_logger()
    logger.info(json.dumps(payload, ensure_ascii=False))
