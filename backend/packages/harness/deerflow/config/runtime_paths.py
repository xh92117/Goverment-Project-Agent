"""Runtime path resolution for standalone harness usage."""

import os
from pathlib import Path

AGENT_BASE_HOME_ENV = "AGENT_BASE_HOME"
AGENT_BASE_PROJECT_ROOT_ENV = "AGENT_BASE_PROJECT_ROOT"
LEGACY_HOME_ENV = "DEER_FLOW_HOME"
LEGACY_PROJECT_ROOT_ENV = "DEER_FLOW_PROJECT_ROOT"
STATE_DIR_NAME = ".agent-base"
LEGACY_STATE_DIR_NAME = ".deer-flow"


def project_root() -> Path:
    """Return the caller project root for runtime-owned files."""
    if env_root := os.getenv(AGENT_BASE_PROJECT_ROOT_ENV) or os.getenv(LEGACY_PROJECT_ROOT_ENV):
        root = Path(env_root).resolve()
        if not root.exists():
            raise ValueError(f"Project root is set to '{env_root}', but the resolved path '{root}' does not exist.")
        if not root.is_dir():
            raise ValueError(f"Project root is set to '{env_root}', but the resolved path '{root}' is not a directory.")
        return root
    return Path.cwd().resolve()


def runtime_home() -> Path:
    """Return the writable Agent Base state directory."""
    if env_home := os.getenv(AGENT_BASE_HOME_ENV) or os.getenv(LEGACY_HOME_ENV):
        return Path(env_home).resolve()
    root = project_root()
    home = root / STATE_DIR_NAME
    legacy_home = root / LEGACY_STATE_DIR_NAME
    if legacy_home.exists() and not home.exists():
        return legacy_home
    return home


def resolve_path(value: str | os.PathLike[str], *, base: Path | None = None) -> Path:
    """Resolve absolute paths as-is and relative paths against the project root."""
    path = Path(value)
    if not path.is_absolute():
        path = (base or project_root()) / path
    return path.resolve()


def existing_project_file(names: tuple[str, ...]) -> Path | None:
    """Return the first existing named file under the project root."""
    root = project_root()
    for name in names:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None
