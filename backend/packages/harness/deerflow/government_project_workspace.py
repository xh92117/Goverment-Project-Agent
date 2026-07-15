"""Workspace paths for the government project declaration agent."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_USER_ROOT = Path(r"C:\Users\Administrator\GP Agent")
DEFAULT_WORKSPACE_ROOT = DEFAULT_USER_ROOT / "workspace"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _ensure_outside_code_tree(path: Path, *, purpose: str) -> Path:
    resolved = path.resolve()
    code_root = repo_root().resolve()
    try:
        resolved.relative_to(code_root)
    except ValueError:
        return resolved
    raise ValueError(
        f"{purpose} must be outside the source-code tree. "
        f"Got {resolved}; source tree is {code_root}. "
        "Set the runtime path to C:\\Users\\Administrator\\GP Agent\\workspace or another external workspace."
    )


def _runtime_path_from_env(env_name: str, default: Path, *, purpose: str) -> Path:
    raw = os.getenv(env_name)
    path = Path(raw) if raw else default
    return _ensure_outside_code_tree(path, purpose=purpose)


def government_project_workspace_root() -> Path:
    return _runtime_path_from_env(
        "GOVERNMENT_PROJECT_WORKSPACE_ROOT",
        DEFAULT_WORKSPACE_ROOT,
        purpose="Government project workspace root",
    )


def government_project_knowledge_root() -> Path:
    return _runtime_path_from_env(
        "AGENT_BASE_KNOWLEDGE_ROOT",
        government_project_workspace_root() / "knowledge_base",
        purpose="Government project knowledge-base root",
    )


def government_project_drafts_root() -> Path:
    return _runtime_path_from_env(
        "GOVERNMENT_PROJECT_DRAFTS_ROOT",
        government_project_workspace_root() / "proposal_drafts",
        purpose="Government project proposal-drafts root",
    )


def government_project_projects_root() -> Path:
    return _runtime_path_from_env(
        "GOVERNMENT_PROJECT_PROJECTS_ROOT",
        government_project_workspace_root() / "projects",
        purpose="Government project projects root",
    )


def government_project_logs_root() -> Path:
    return _runtime_path_from_env(
        "GOVERNMENT_PROJECT_LOG_ROOT",
        government_project_workspace_root() / "logs",
        purpose="Government project logs root",
    )
