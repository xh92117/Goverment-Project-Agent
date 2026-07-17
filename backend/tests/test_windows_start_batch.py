from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
START_BATCH_PATH = REPO_ROOT / "start.bat"
START_SCRIPT_PATH = REPO_ROOT / "start_web_agent.py"


def _batch_text() -> str:
    return START_BATCH_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_start_batch_checks_before_installing_and_launching() -> None:
    batch = _batch_text()

    assert 'cd /d "%~dp0"' in batch
    assert "call :check_project_dependencies" in batch
    assert "call :install_project_dependencies" in batch
    assert "uv sync --locked --link-mode copy" in batch
    assert "pnpm install --frozen-lockfile --reporter=append-only" in batch
    assert '".venv\\Scripts\\python.exe" "start_web_agent.py" %*' in batch
    assert "--force" not in batch


def test_start_batch_validates_backend_frontend_and_dependency_state() -> None:
    batch = _batch_text()

    assert "from PIL import Image" in batch
    assert "from app.gateway.app import app" in batch
    assert "frontend\\node_modules\\next\\dist\\bin\\next" in batch
    assert "backend\\uv.lock" in batch
    assert "frontend\\pnpm-lock.yaml" in batch
    assert "frontend\\package.json" in batch


def test_default_user_root_uses_the_active_user_home(monkeypatch, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("gp_start_web_agent", START_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module.Path, "home", classmethod(lambda _cls: tmp_path))

    assert module.default_user_root() == tmp_path / "GP Agent"


def test_start_environment_derives_all_paths_from_gp_agent_home(monkeypatch, tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("gp_start_web_agent_env", START_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "custom-gp-agent"
    monkeypatch.setattr(module.os, "environ", {})
    monkeypatch.setattr(module, "load_dotenv", lambda env: env.update({"GP_AGENT_HOME": str(root)}))

    env = module.build_env(
        SimpleNamespace(
            log_dir=None,
            host="127.0.0.1",
            backend_port=10086,
            frontend_port=9527,
            network_proxy="",
        )
    )

    assert env["AGENT_BASE_HOME"] == str(root / ".agent-base")
    assert env["GOVERNMENT_PROJECT_WORKSPACE_ROOT"] == str(root / "workspace")
    assert env["AGENT_BASE_KNOWLEDGE_ROOT"] == str(root / "workspace" / "knowledge_base")
    assert env["GOVERNMENT_PROJECT_DRAFTS_ROOT"] == str(root / "workspace" / "proposal_drafts")
    assert env["GOVERNMENT_PROJECT_PROJECTS_ROOT"] == str(root / "workspace" / "projects")
    assert env["GOVERNMENT_PROJECT_LOG_ROOT"] == str(root / "logs")


def test_start_defaults_to_opening_browser(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location("gp_start_web_agent_browser_args", START_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.sys, "argv", [str(START_SCRIPT_PATH)])

    args = module.parse_args()

    assert args.no_open_browser is False


def test_open_default_browser_uses_system_browser() -> None:
    spec = importlib.util.spec_from_file_location("gp_start_web_agent_browser", START_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with patch.object(module.webbrowser, "open", return_value=True) as browser_open:
        assert module.open_default_browser("http://127.0.0.1:9527") is True

    browser_open.assert_called_once_with("http://127.0.0.1:9527", new=2, autoraise=True)


def test_warmup_covers_all_primary_frontend_modules() -> None:
    spec = importlib.util.spec_from_file_location("gp_start_web_agent_warmup", START_SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = SimpleNamespace(host="127.0.0.1", frontend_port=9527, backend_port=10086, warmup_timeout=45.0)

    warmed: list[str] = []
    with (
        patch.object(module, "first_project_and_thread", return_value=(None, None)),
        patch.object(module, "request_page", side_effect=lambda url, **_kwargs: warmed.append(url)),
    ):
        module.warm_frontend_routes(args)

    assert warmed == [
        "http://127.0.0.1:9527/login",
        "http://127.0.0.1:9527/setup",
        "http://127.0.0.1:9527/workspace/projects",
        "http://127.0.0.1:9527/workspace/knowledge",
        "http://127.0.0.1:9527/workspace/drafts",
        "http://127.0.0.1:9527/workspace/settings",
        "http://127.0.0.1:9527/workspace/chat",
        "http://127.0.0.1:9527/workspace/agents/government-project-declaration/chats/new",
    ]
