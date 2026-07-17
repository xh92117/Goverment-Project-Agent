"""Workspace paths for the government project declaration agent."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

GP_AGENT_HOME_ENV = "GP_AGENT_HOME"
RUNTIME_HOME_ENV = "AGENT_BASE_HOME"
HOST_BASE_DIR_ENV = "AGENT_BASE_HOST_BASE_DIR"
WORKSPACE_ROOT_ENV = "GOVERNMENT_PROJECT_WORKSPACE_ROOT"
KNOWLEDGE_ROOT_ENV = "AGENT_BASE_KNOWLEDGE_ROOT"
DRAFTS_ROOT_ENV = "GOVERNMENT_PROJECT_DRAFTS_ROOT"
PROJECTS_ROOT_ENV = "GOVERNMENT_PROJECT_PROJECTS_ROOT"
LOG_ROOT_ENV = "GOVERNMENT_PROJECT_LOG_ROOT"
DB_PATH_ENV = "AGENT_BASE_DB_PATH"


@dataclass(frozen=True)
class GovernmentProjectPaths:
    """Resolved external directories used by the declaration agent."""

    gp_agent_home: Path
    runtime_home: Path
    host_base_dir: Path
    workspace_root: Path
    knowledge_root: Path
    drafts_root: Path
    projects_root: Path
    logs_root: Path
    db_path: Path


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
        f"Set {GP_AGENT_HOME_ENV} or the related path variable to another external directory."
    )


def _runtime_path_from_values(
    values: Mapping[str, str],
    env_name: str,
    default: Path,
    *,
    purpose: str,
    allow_inside_source: bool = False,
) -> Path:
    raw = str(values.get(env_name) or "").strip()
    path = Path(raw).expanduser() if raw else default
    return path.resolve() if allow_inside_source else _ensure_outside_code_tree(path, purpose=purpose)


def resolve_government_project_paths(
    values: Mapping[str, str] | None = None,
    *,
    user_home: Path | None = None,
    allow_runtime_inside_source: bool = True,
) -> GovernmentProjectPaths:
    """Resolve all government-project paths from environment-style values.

    ``GP_AGENT_HOME`` is the friendly top-level override. Individual path
    variables remain available for installations that split data across disks.
    """

    env = os.environ if values is None else values
    configured_home = str(env.get(GP_AGENT_HOME_ENV) or "").strip()
    if configured_home:
        gp_agent_home = _ensure_outside_code_tree(
            Path(configured_home).expanduser(),
            purpose="GP Agent home",
        )
    else:
        gp_agent_home = _ensure_outside_code_tree(
            (user_home or Path.home()) / "GP Agent",
            purpose="GP Agent home",
        )
    runtime_home = _runtime_path_from_values(
        env,
        RUNTIME_HOME_ENV,
        gp_agent_home / ".agent-base",
        purpose="Agent Base runtime home",
        allow_inside_source=allow_runtime_inside_source,
    )
    host_base_dir = _runtime_path_from_values(
        env,
        HOST_BASE_DIR_ENV,
        runtime_home,
        purpose="Agent Base host runtime home",
        allow_inside_source=allow_runtime_inside_source,
    )
    workspace_root = _runtime_path_from_values(
        env,
        WORKSPACE_ROOT_ENV,
        gp_agent_home / "workspace",
        purpose="Government project workspace root",
    )
    knowledge_root = _runtime_path_from_values(
        env,
        KNOWLEDGE_ROOT_ENV,
        workspace_root / "knowledge_base",
        purpose="Government project knowledge-base root",
    )
    drafts_root = _runtime_path_from_values(
        env,
        DRAFTS_ROOT_ENV,
        workspace_root / "proposal_drafts",
        purpose="Government project proposal-drafts root",
    )
    projects_root = _runtime_path_from_values(
        env,
        PROJECTS_ROOT_ENV,
        workspace_root / "projects",
        purpose="Government project projects root",
    )
    logs_root = _runtime_path_from_values(
        env,
        LOG_ROOT_ENV,
        gp_agent_home / "logs",
        purpose="Government project logs root",
    )
    db_path = _runtime_path_from_values(
        env,
        DB_PATH_ENV,
        runtime_home / "data" / "agent_base.db",
        purpose="Agent Base database path",
        allow_inside_source=allow_runtime_inside_source,
    )
    return GovernmentProjectPaths(
        gp_agent_home=gp_agent_home,
        runtime_home=runtime_home,
        host_base_dir=host_base_dir,
        workspace_root=workspace_root,
        knowledge_root=knowledge_root,
        drafts_root=drafts_root,
        projects_root=projects_root,
        logs_root=logs_root,
        db_path=db_path,
    )


def gp_agent_home() -> Path:
    return resolve_government_project_paths().gp_agent_home


def government_project_workspace_root() -> Path:
    return resolve_government_project_paths().workspace_root


def government_project_knowledge_root() -> Path:
    return resolve_government_project_paths().knowledge_root


def government_project_drafts_root() -> Path:
    return resolve_government_project_paths().drafts_root


def government_project_projects_root() -> Path:
    return resolve_government_project_paths().projects_root


def government_project_logs_root() -> Path:
    return resolve_government_project_paths().logs_root
