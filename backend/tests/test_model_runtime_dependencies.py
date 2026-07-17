from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PYPROJECT_PATH = REPO_ROOT / "backend" / "packages" / "harness" / "pyproject.toml"
START_BATCH_PATH = REPO_ROOT / "start.bat"


def test_core_model_adapters_are_harness_base_dependencies() -> None:
    pyproject = tomllib.loads(HARNESS_PYPROJECT_PATH.read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    for package in ("langchain-anthropic", "langchain-deepseek", "langchain-openai"):
        assert any(dependency.lower().startswith(package) for dependency in dependencies)


def test_windows_startup_probe_imports_core_model_adapters() -> None:
    batch = START_BATCH_PATH.read_text(encoding="utf-8")

    assert "from langchain_anthropic import ChatAnthropic" in batch
    assert "from langchain_deepseek import ChatDeepSeek" in batch
    assert "from langchain_openai import ChatOpenAI" in batch
