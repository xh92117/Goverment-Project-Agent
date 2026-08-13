import importlib.util
from pathlib import Path


def _load_limits_module():
    module_name = "_agent_base_sandbox_limits_under_test"
    repo_root = Path(__file__).resolve().parents[2]
    limits_path = repo_root / "backend" / "packages" / "harness" / "deerflow" / "sandbox" / "limits.py"
    spec = importlib.util.spec_from_file_location(module_name, limits_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_effective_write_file_max_bytes_defaults_to_safe_cap(monkeypatch):
    limits = _load_limits_module()
    monkeypatch.delenv("AGENT_BASE_WRITE_FILE_MAX_BYTES", raising=False)
    monkeypatch.delenv("DEERFLOW_WRITE_FILE_MAX_BYTES", raising=False)

    assert limits.effective_write_file_max_bytes() == 80 * 1024


def test_effective_write_file_max_bytes_prefers_agent_base_env(monkeypatch):
    limits = _load_limits_module()
    monkeypatch.setenv("AGENT_BASE_WRITE_FILE_MAX_BYTES", "92160")
    monkeypatch.setenv("DEERFLOW_WRITE_FILE_MAX_BYTES", "307200")

    assert limits.effective_write_file_max_bytes() == 92160


def test_effective_write_file_max_bytes_falls_back_to_legacy_env(monkeypatch):
    limits = _load_limits_module()
    monkeypatch.delenv("AGENT_BASE_WRITE_FILE_MAX_BYTES", raising=False)
    monkeypatch.setenv("DEERFLOW_WRITE_FILE_MAX_BYTES", "307200")

    assert limits.effective_write_file_max_bytes() == 307200


def test_effective_write_file_max_bytes_ignores_malformed_env(monkeypatch):
    limits = _load_limits_module()
    monkeypatch.setenv("AGENT_BASE_WRITE_FILE_MAX_BYTES", "lots")

    assert limits.effective_write_file_max_bytes() == 80 * 1024
