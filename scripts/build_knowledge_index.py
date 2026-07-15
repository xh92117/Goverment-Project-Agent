"""Build LLM-Wiki knowledge indexes from a UTF-8 JSON config.

This script exists mainly to avoid Windows PowerShell encoding pitfalls with
Chinese folder names, categories, domains, and proposal chapter names. Prefer
passing Chinese values through a UTF-8 JSON config file instead of command-line
arguments.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_USER_ROOT = Path(r"C:\Users\Administrator\GP Agent")
DEFAULT_RUNTIME_HOME = DEFAULT_USER_ROOT / ".agent-base"
DEFAULT_WORKSPACE_ROOT = DEFAULT_USER_ROOT / "workspace"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_outside_code_tree(path: Path, *, purpose: str) -> Path:
    resolved = path.resolve()
    repo = _repo_root().resolve()
    try:
        resolved.relative_to(repo)
    except ValueError:
        return resolved
    raise ValueError(f"{purpose} must be outside the source-code tree. Got {resolved}; source tree is {repo}.")


def _configure_imports() -> None:
    repo = _repo_root()
    harness = repo / "backend" / "packages" / "harness"
    backend = repo / "backend"
    for path in (str(harness), str(backend)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _validate_runtime_env_paths() -> None:
    for env_name, purpose in (
        ("AGENT_BASE_HOME", "AGENT_BASE_HOME"),
        ("DEER_FLOW_HOME", "DEER_FLOW_HOME"),
        ("GOVERNMENT_PROJECT_WORKSPACE_ROOT", "GOVERNMENT_PROJECT_WORKSPACE_ROOT"),
        ("AGENT_BASE_KNOWLEDGE_ROOT", "AGENT_BASE_KNOWLEDGE_ROOT"),
    ):
        value = os.environ.get(env_name)
        if value:
            os.environ[env_name] = str(_ensure_outside_code_tree(Path(value), purpose=purpose))


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object.")
    return data


def _merge_cli(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    merged = dict(config)
    for key in (
        "root",
        "folder_path",
        "category",
        "domain",
        "user_id",
    ):
        value = getattr(args, key)
        if value is not None:
            merged[key] = value
    if args.project_type:
        merged["project_types"] = args.project_type
    if args.non_recursive:
        merged["recursive"] = False
    if args.no_replace_existing:
        merged["replace_existing"] = False
    return merged


def main() -> int:
    _configure_stdio()
    _configure_imports()
    runtime_home = _ensure_outside_code_tree(DEFAULT_RUNTIME_HOME, purpose="AGENT_BASE_HOME")
    workspace_root = _ensure_outside_code_tree(DEFAULT_WORKSPACE_ROOT, purpose="GOVERNMENT_PROJECT_WORKSPACE_ROOT")
    knowledge_root = _ensure_outside_code_tree(workspace_root / "knowledge_base", purpose="AGENT_BASE_KNOWLEDGE_ROOT")
    os.environ.setdefault("AGENT_BASE_PROJECT_ROOT", str(_repo_root()))
    os.environ.setdefault("AGENT_BASE_HOME", str(runtime_home))
    os.environ.setdefault("DEER_FLOW_HOME", os.environ["AGENT_BASE_HOME"])
    os.environ.setdefault("GOVERNMENT_PROJECT_WORKSPACE_ROOT", str(workspace_root))
    os.environ.setdefault("AGENT_BASE_KNOWLEDGE_ROOT", str(knowledge_root))

    parser = argparse.ArgumentParser(description="Build LLM-Wiki knowledge indexes.")
    parser.add_argument("--config", type=Path, help="UTF-8 JSON config file.")
    parser.add_argument("--root", help="Knowledge-base root directory.")
    parser.add_argument("--folder-path", dest="folder_path", help="Folder path relative to knowledge root.")
    parser.add_argument("--category", help="Override index category.")
    parser.add_argument("--domain", help="Override index domain.")
    parser.add_argument("--project-type", action="append", help="Project type. Can be passed multiple times.")
    parser.add_argument("--user-id", dest="user_id", default=None, help="User id for scoped index storage.")
    parser.add_argument("--non-recursive", action="store_true", help="Scan only direct child files.")
    parser.add_argument("--no-replace-existing", action="store_true", help="Do not update existing entries with the same file path.")
    args = parser.parse_args()

    config = _load_json(args.config) if args.config else {}
    config = _merge_cli(args, config)

    root = config.get("root")
    if root:
        os.environ["AGENT_BASE_KNOWLEDGE_ROOT"] = str(Path(root).expanduser())
    _validate_runtime_env_paths()

    from deerflow.knowledge import (
        KnowledgeIndexBuildRequest,
        build_knowledge_index_from_folder,
        organize_incoming_files,
        organize_options_from_config,
    )

    user_id = config.get("user_id")
    organization = None
    if config.get("organize_incoming", False):
        organization = organize_incoming_files(
            organize_options_from_config(config),
            user_id=user_id,
        )

    request = KnowledgeIndexBuildRequest(
        folder_path=config.get("folder_path", ""),
        recursive=config.get("recursive", True),
        include_extensions=config.get("include_extensions", [".md", ".markdown", ".txt", ".docx", ".pdf", ".xlsx", ".xls", ".csv", ".tsv"]),
        replace_existing=config.get("replace_existing", True),
        category=config.get("category"),
        domain=config.get("domain"),
        project_types=config.get("project_types", []),
        max_files=config.get("max_files", 200),
        incremental=config.get("incremental", True),
    )
    result = build_knowledge_index_from_folder(request, user_id=user_id)
    output: dict[str, Any] = {
        "organization": dataclasses.asdict(organization) if organization else None,
        "index_build": result.model_dump(mode="json"),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
