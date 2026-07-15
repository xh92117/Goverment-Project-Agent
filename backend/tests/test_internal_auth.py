"""Tests for Gateway internal auth token handling."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_internal_auth_module():
    module_path = Path(__file__).resolve().parents[1] / "app" / "gateway" / "internal_auth.py"
    spec = importlib.util.spec_from_file_location("agent_base_test_internal_auth", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_internal_auth_uses_legacy_shared_env_token(monkeypatch):
    monkeypatch.delenv("AGENT_BASE_INTERNAL_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", "shared-token")
    reloaded = _load_internal_auth_module()
    try:
        headers = reloaded.create_internal_auth_headers()

        assert headers[reloaded.INTERNAL_AUTH_HEADER_NAME] == "shared-token"
        assert reloaded.is_valid_internal_auth_token("shared-token") is True
        assert reloaded.is_valid_internal_auth_token("other-token") is False
    finally:
        monkeypatch.delenv("AGENT_BASE_INTERNAL_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", raising=False)
        _load_internal_auth_module()


def test_internal_auth_prefers_agent_base_env_token(monkeypatch):
    monkeypatch.setenv("AGENT_BASE_INTERNAL_AUTH_TOKEN", "agent-base-token")
    monkeypatch.setenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", "legacy-token")
    reloaded = _load_internal_auth_module()
    try:
        headers = reloaded.create_internal_auth_headers()

        assert headers[reloaded.INTERNAL_AUTH_HEADER_NAME] == "agent-base-token"
        assert reloaded.is_valid_internal_auth_token("agent-base-token") is True
        assert reloaded.is_valid_internal_auth_token("legacy-token") is False
    finally:
        monkeypatch.delenv("AGENT_BASE_INTERNAL_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", raising=False)
        _load_internal_auth_module()


def test_internal_auth_generates_process_local_fallback(monkeypatch):
    monkeypatch.delenv("AGENT_BASE_INTERNAL_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("DEER_FLOW_INTERNAL_AUTH_TOKEN", raising=False)
    reloaded = _load_internal_auth_module()
    try:
        token = reloaded.create_internal_auth_headers()[reloaded.INTERNAL_AUTH_HEADER_NAME]

        assert token
        assert reloaded.is_valid_internal_auth_token(token) is True
    finally:
        _load_internal_auth_module()
