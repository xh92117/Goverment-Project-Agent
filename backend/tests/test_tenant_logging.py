from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from deerflow.config.paths import Paths
from deerflow.runtime.tenant_logging import TenantLogHandler, append_tenant_audit_event
from deerflow.runtime.user_context import reset_current_user, set_current_user


def _read_json_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_tenant_log_handler_separates_users(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    monkeypatch.setattr("deerflow.runtime.tenant_logging.get_paths", lambda: paths)
    handler = TenantLogHandler()

    for user_id, message in (("tenant-a", "alpha secret"), ("tenant-b", "beta secret")):
        token = set_current_user(SimpleNamespace(id=user_id))
        try:
            handler.emit(logging.LogRecord("test", logging.INFO, __file__, 1, message, (), None))
        finally:
            reset_current_user(token)

    tenant_a_log = paths.user_logs_dir("tenant-a") / "application.jsonl"
    tenant_b_log = paths.user_logs_dir("tenant-b") / "application.jsonl"
    records_a = _read_json_lines(tenant_a_log)
    records_b = _read_json_lines(tenant_b_log)

    assert [record["message"] for record in records_a] == ["alpha secret"]
    assert [record["message"] for record in records_b] == ["beta secret"]
    assert records_a[0]["user_id"] == "tenant-a"
    assert records_b[0]["user_id"] == "tenant-b"


def test_audit_events_are_written_to_the_named_users_log_only(tmp_path, monkeypatch):
    paths = Paths(tmp_path)
    monkeypatch.setattr("deerflow.runtime.tenant_logging.get_paths", lambda: paths)

    append_tenant_audit_event(
        user_id="tenant-a",
        action="http_request",
        details={"method": "POST", "path": "/api/projects", "status_code": 201},
    )

    audit_path = paths.user_logs_dir("tenant-a") / "audit.jsonl"
    records = _read_json_lines(audit_path)
    assert records[0]["user_id"] == "tenant-a"
    assert records[0]["action"] == "http_request"
    assert not (paths.user_logs_dir("tenant-b") / "audit.jsonl").exists()
