import importlib.util
from pathlib import Path


def _load_script_module(relative_path: str, module_name: str):
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _assert_hermetic_env(monkeypatch, module, tmp_path):
    home = tmp_path / "home"
    cfg = home / "config.yaml"
    extensions = home / "extensions_config.json"
    for key in (
        "AGENT_BASE_HOME",
        "AGENT_BASE_CONFIG_PATH",
        "AGENT_BASE_EXTENSIONS_CONFIG_PATH",
        "DEER_FLOW_HOME",
        "DEER_FLOW_CONFIG_PATH",
        "DEER_FLOW_EXTENSIONS_CONFIG_PATH",
    ):
        monkeypatch.setenv(key, "outer-value")

    module._set_hermetic_agent_base_env(
        home=home,
        config_path=cfg,
        extensions_config_path=extensions,
    )

    assert module.os.environ["AGENT_BASE_HOME"] == str(home)
    assert module.os.environ["AGENT_BASE_CONFIG_PATH"] == str(cfg)
    assert module.os.environ["AGENT_BASE_EXTENSIONS_CONFIG_PATH"] == str(extensions)
    assert module.os.environ["DEER_FLOW_HOME"] == str(home)
    assert module.os.environ["DEER_FLOW_CONFIG_PATH"] == str(cfg)
    assert module.os.environ["DEER_FLOW_EXTENSIONS_CONFIG_PATH"] == str(extensions)


def test_record_gateway_sets_agent_base_env_and_legacy_aliases(monkeypatch, tmp_path):
    module = _load_script_module("backend/scripts/record_gateway.py", "_record_gateway_env_test")

    _assert_hermetic_env(monkeypatch, module, tmp_path)


def test_replay_gateway_sets_agent_base_env_and_legacy_aliases(monkeypatch, tmp_path):
    module = _load_script_module("backend/scripts/run_replay_gateway.py", "_run_replay_gateway_env_test")

    _assert_hermetic_env(monkeypatch, module, tmp_path)


def test_record_gateway_prefers_agent_base_record_out(monkeypatch, tmp_path):
    module = _load_script_module("backend/scripts/record_gateway.py", "_record_gateway_record_out_test")
    monkeypatch.setenv("AGENT_BASE_RECORD_OUT", str(tmp_path / "agent-base.jsonl"))
    monkeypatch.setenv("DEERFLOW_RECORD_OUT", str(tmp_path / "legacy.jsonl"))

    assert module._resolve_record_out() == str(tmp_path / "agent-base.jsonl")


def test_record_gateway_falls_back_to_legacy_record_out(monkeypatch, tmp_path):
    module = _load_script_module("backend/scripts/record_gateway.py", "_record_gateway_legacy_record_out_test")
    monkeypatch.delenv("AGENT_BASE_RECORD_OUT", raising=False)
    monkeypatch.setenv("DEERFLOW_RECORD_OUT", str(tmp_path / "legacy.jsonl"))

    assert module._resolve_record_out() == str(tmp_path / "legacy.jsonl")


def test_replay_gateway_seed_flag_accepts_agent_base_name(monkeypatch):
    module = _load_script_module("backend/scripts/run_replay_gateway.py", "_run_replay_gateway_seed_test")
    monkeypatch.setenv("AGENT_BASE_ENABLE_TEST_SEED", "1")
    monkeypatch.delenv("DEERFLOW_ENABLE_TEST_SEED", raising=False)

    assert module._is_test_seed_enabled() is True


def test_replay_gateway_seed_flag_accepts_legacy_name(monkeypatch):
    module = _load_script_module("backend/scripts/run_replay_gateway.py", "_run_replay_gateway_legacy_seed_test")
    monkeypatch.delenv("AGENT_BASE_ENABLE_TEST_SEED", raising=False)
    monkeypatch.setenv("DEERFLOW_ENABLE_TEST_SEED", "1")

    assert module._is_test_seed_enabled() is True
