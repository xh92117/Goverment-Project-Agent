"""Small, formatting-preserving helpers for project ``.env`` files."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

_SAFE_ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,\-]+$")


def env_path_for_config(config_path: Path) -> Path:
    """Return the project .env next to config.yaml."""
    return config_path.parent / ".env"


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
        if raw.strip().startswith('"'):
            value = value.replace(r"\"", '"').replace(r"\\", "\\")
    return value


def read_env_file(env_path: Path) -> dict[str, str]:
    """Read simple KEY=value entries while ignoring comments and blank lines."""
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _parse_env_value(value)
    return values


def _format_env_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail="Environment values cannot contain newlines")
    if value and _SAFE_ENV_VALUE_RE.fullmatch(value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', r"\"") + '"'


def write_env_values(env_path: Path, updates: dict[str, str | None]) -> None:
    """Update selected keys without rewriting unrelated .env content."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        prefix = ""
        line = stripped
        if line.startswith("export "):
            prefix = "export "
            line = line.removeprefix("export ").lstrip()
        if not line or line.startswith("#") or "=" not in line:
            output.append(raw_line)
            continue

        key = line.split("=", 1)[0].strip()
        if key not in updates:
            output.append(raw_line)
            continue

        seen.add(key)
        value = updates[key]
        if value is None:
            continue
        output.append(f"{prefix}{key}={_format_env_value(value)}")

    for key, value in updates.items():
        if key in seen or value is None:
            continue
        output.append(f"{key}={_format_env_value(value)}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
