"""Tenant-scoped structured application and audit logs.

Operational stdout remains a deployment concern. This module creates an
additional private JSONL stream only while an authenticated user context is
active, so request work can be inspected without mixing tenants on disk.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import get_current_user

_write_lock = threading.Lock()
_handler_lock = threading.Lock()
_HANDLER_MARKER = "_deerflow_tenant_log_handler"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _append_json_line(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{encoded}\n")


class TenantLogHandler(logging.Handler):
    """Mirror records emitted in a user context to that user's JSONL file."""

    def emit(self, record: logging.LogRecord) -> None:
        user = get_current_user()
        if user is None:
            return
        try:
            payload: dict[str, Any] = {
                "timestamp": _timestamp(),
                "user_id": user.id,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if record.exc_info:
                payload["exception"] = self.formatException(record.exc_info)
            _append_json_line(get_paths().user_logs_dir(user.id) / "application.jsonl", payload)
        except Exception:
            self.handleError(record)

    @staticmethod
    def formatException(exc_info) -> str:  # noqa: N802 - mirrors logging.Formatter API
        return logging.Formatter().formatException(exc_info)


def configure_tenant_logging() -> TenantLogHandler:
    """Attach exactly one tenant handler to the process root logger."""
    root = logging.getLogger()
    with _handler_lock:
        for handler in root.handlers:
            if getattr(handler, _HANDLER_MARKER, False):
                return handler  # type: ignore[return-value]
        handler = TenantLogHandler()
        setattr(handler, _HANDLER_MARKER, True)
        root.addHandler(handler)
        return handler


def append_tenant_audit_event(*, user_id: str, action: str, details: dict[str, Any]) -> None:
    """Append an immutable-style structured audit event to one tenant bucket."""
    payload = {
        "timestamp": _timestamp(),
        "user_id": user_id,
        "action": action,
        "details": details,
    }
    _append_json_line(get_paths().user_logs_dir(user_id) / "audit.jsonl", payload)
