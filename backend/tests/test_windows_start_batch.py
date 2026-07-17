from __future__ import annotations

import importlib.util
from pathlib import Path

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

    assert "from PIL import Image; from app.gateway.app import app" in batch
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
