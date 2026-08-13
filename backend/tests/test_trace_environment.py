import importlib.util
import sys
import types
from pathlib import Path


def _load_metadata_module():
    module_name = "_agent_base_tracing_metadata_under_test"
    repo_root = Path(__file__).resolve().parents[2]
    metadata_path = repo_root / "backend" / "packages" / "harness" / "deerflow" / "tracing" / "metadata.py"

    deerflow_config = types.ModuleType("deerflow.config")
    deerflow_config.get_enabled_tracing_providers = lambda: []
    sys.modules.setdefault("deerflow.config", deerflow_config)

    spec = importlib.util.spec_from_file_location(module_name, metadata_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_resolve_trace_environment_prefers_explicit_value(monkeypatch):
    metadata = _load_metadata_module()
    monkeypatch.setenv("AGENT_BASE_ENV", "agent-base")

    assert metadata.resolve_trace_environment("explicit") == "explicit"


def test_resolve_trace_environment_prefers_agent_base_env(monkeypatch):
    metadata = _load_metadata_module()
    monkeypatch.setenv("AGENT_BASE_ENV", "agent-base")
    monkeypatch.setenv("DEER_FLOW_ENV", "legacy")
    monkeypatch.setenv("ENVIRONMENT", "generic")

    assert metadata.resolve_trace_environment() == "agent-base"


def test_resolve_trace_environment_falls_back_to_legacy_then_generic(monkeypatch):
    metadata = _load_metadata_module()
    monkeypatch.setenv("DEER_FLOW_ENV", "legacy")
    monkeypatch.setenv("ENVIRONMENT", "generic")

    assert metadata.resolve_trace_environment() == "legacy"

    monkeypatch.delenv("DEER_FLOW_ENV", raising=False)

    assert metadata.resolve_trace_environment() == "generic"
