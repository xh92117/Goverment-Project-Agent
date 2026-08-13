"""Tools for saving government proposal drafts as Markdown workspace files."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.runtime.user_context import resolve_runtime_user_id, strict_user_context_enabled
from deerflow.tools.types import Runtime

_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")
_THREAD_ID_RE = re.compile(r"[^0-9A-Za-z._-]+")
_THREAD_PROJECT_MARKER = ".thread_project.json"
_PROJECT_META_FILE = ".project.json"


def _proposal_workspace_root(runtime: Runtime) -> Path:
    """Return the current runtime user's private legacy-drafts root."""
    return get_paths().user_drafts_dir(resolve_runtime_user_id(runtime)).resolve()


def _safe_name(value: str, fallback: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", value.strip()).strip("._ ")
    return cleaned or fallback


def _safe_thread_id(value: str) -> str:
    cleaned = _THREAD_ID_RE.sub("_", value.strip()).strip("._ ")
    return cleaned or "unknown-thread"


def _extract_project_context(runtime: Runtime) -> tuple[str, str] | None:
    context = getattr(runtime, "context", None) or {}
    if not isinstance(context, dict):
        return None
    project_id = context.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        return None
    project_name = context.get("project_name")
    name = project_name if isinstance(project_name, str) and project_name.strip() else project_id
    return _safe_thread_id(project_id), _safe_name(name, "default-proposal")


def _project_meta_dir(project_id: str, runtime: Runtime) -> Path:
    user_id = resolve_runtime_user_id(runtime)
    return (get_paths().user_projects_dir(user_id) / project_id).resolve()


def _project_root_from_metadata(meta_dir: Path, runtime: Runtime) -> Path:
    meta_path = meta_dir / _PROJECT_META_FILE
    if not meta_path.exists():
        return meta_dir
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return meta_dir
    if not isinstance(data, dict):
        return meta_dir
    root_path = data.get("root_path")
    if isinstance(root_path, str) and root_path.strip():
        resolved = Path(root_path).expanduser().resolve()
        if strict_user_context_enabled():
            user_root = get_paths().user_dir(resolve_runtime_user_id(runtime)).resolve()
            try:
                resolved.relative_to(user_root)
            except ValueError:
                return meta_dir
        return resolved
    return meta_dir


def _ensure_project_metadata(
    meta_dir: Path,
    project_root: Path,
    project_id: str,
    project_name: str,
    owner_id: str,
) -> None:
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / _PROJECT_META_FILE
    if meta_path.exists():
        return
    now = datetime.now(UTC).isoformat()
    meta_path.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "name": project_name,
                "type": "government-project-declaration",
                "status": "active",
                "root_path": str(project_root),
                "created_at": now,
                "updated_at": now,
                "metadata": {},
                "owner_id": owner_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _safe_relative_dir(value: str) -> Path:
    parts = [
        _safe_name(part, "section")
        for part in re.split(r"[\\/]+", value.strip())
        if part.strip()
    ]
    safe_parts = [part for part in parts if part not in {".", ".."}]
    return Path(*safe_parts) if safe_parts else Path()


def _ensure_markdown_filename(value: str) -> str:
    name = _safe_name(value, "section")
    if not name.lower().endswith(".md"):
        name += ".md"
    return name


def _extract_thread_id(runtime: Runtime) -> str | None:
    context = getattr(runtime, "context", None) or {}
    thread_id = context.get("thread_id") if isinstance(context, dict) else None
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()

    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, dict) else None
    return thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None


def _load_thread_project(root: Path, thread_id: str) -> dict[str, str] | None:
    if not root.exists():
        return None
    for candidate in root.iterdir():
        if not candidate.is_dir() or candidate.name.startswith("."):
            continue
        marker = candidate / _THREAD_PROJECT_MARKER
        if not marker.exists():
            continue
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("thread_id") != thread_id:
            continue

        folder_name = data.get("folder_name")
        if not isinstance(folder_name, str) or not folder_name.strip():
            continue

        initial_task_name = data.get("initial_task_name")
        return {
            "folder_name": _safe_name(folder_name, "default-proposal"),
            "initial_task_name": _safe_name(
                str(initial_task_name or folder_name),
                "default-proposal",
            ),
        }
    return None


def _save_thread_project(root: Path, thread_id: str, data: dict[str, str]) -> None:
    project_dir = root / data["folder_name"]
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / _THREAD_PROJECT_MARKER
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _project_scope(root: Path, runtime: Runtime, task_name: str) -> tuple[str, str]:
    """Resolve one stable proposal folder per conversation thread."""
    safe_task = _safe_name(task_name, "default-proposal")
    thread_id = _extract_thread_id(runtime)
    if not thread_id:
        return safe_task, ""

    current = _load_thread_project(root, thread_id)
    if current:
        default_subfolder = "" if safe_task == current["initial_task_name"] else safe_task
        return current["folder_name"], default_subfolder

    folder_name = f"{safe_task}-{_safe_thread_id(thread_id)[:8]}"
    _save_thread_project(
        root,
        thread_id,
        {
            "folder_name": folder_name,
            "initial_task_name": safe_task,
            "thread_id": thread_id,
        },
    )
    return folder_name, ""


def _save_project_scoped_markdown(
    *,
    runtime: Runtime,
    task_name: str,
    section_name: str,
    content: str,
    subfolder_name: str,
    tool_call_id: str,
) -> Command | None:
    project_context = _extract_project_context(runtime)
    if not project_context:
        return None

    project_id, project_name = project_context
    user_id = resolve_runtime_user_id(runtime)
    thread_data = (runtime.state or {}).get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    meta_dir = _project_meta_dir(project_id, runtime)
    project_root = _project_root_from_metadata(meta_dir, runtime)
    drafts_root = (project_root / "drafts").resolve()
    subfolder = _safe_relative_dir(subfolder_name)
    filename = _ensure_markdown_filename(section_name)
    workspace_file = (drafts_root / subfolder / filename).resolve()

    try:
        workspace_file.relative_to(project_root)
    except ValueError:
        return Command(
            update={"messages": [ToolMessage("Error: invalid project workspace path", tool_call_id=tool_call_id)]}
        )

    for folder in ("inputs", "drafts", "outputs", "versions"):
        (project_root / folder).mkdir(parents=True, exist_ok=True)
    _ensure_project_metadata(meta_dir, project_root, project_id, project_name, user_id)
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text(content, encoding="utf-8")

    if not outputs_path:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Saved Markdown draft to project workspace: {workspace_file}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    outputs_root = Path(outputs_path).resolve()
    output_file = (outputs_root / "projects" / project_id / "drafts" / subfolder / filename).resolve()
    try:
        output_file.relative_to(outputs_root)
    except ValueError:
        return Command(
            update={"messages": [ToolMessage("Error: invalid artifact output path", tool_call_id=tool_call_id)]}
        )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(workspace_file, output_file)

    artifact_parts = [project_id, "drafts", *subfolder.parts, filename]
    artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/projects/{'/'.join(artifact_parts)}"
    return Command(
        update={
            "artifacts": [artifact_path],
            "messages": [
                ToolMessage(
                    f"Saved Markdown draft to {workspace_file} and presented {artifact_path}",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


@tool("proposal_save_markdown", parse_docstring=True)
def proposal_save_markdown_tool(
    runtime: Runtime,
    task_name: str,
    section_name: str,
    content: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    subfolder_name: str = "",
) -> Command:
    """Save a proposal draft section as Markdown and present it in the front end.

    Use this tool after generating or revising a government project declaration
    section. For a chat thread, the first call creates one stable project folder
    under `workspace/proposal_drafts`; later calls in the same thread reuse that
    folder. Drafts may be organized into subfolders under that project folder,
    and a copy is placed in the current thread outputs so the front-end
    Artifacts panel can preview it.

    Args:
        task_name: Proposal task or project name. The first value in a chat fixes the project folder.
        section_name: Proposal section name, such as 国内外研究现状 or 技术路线. Used as the Markdown filename.
        content: Markdown content to save.
        subfolder_name: Optional subfolder under the project folder, such as 研究方案 or 预算/设备费.
    """
    project_scoped = _save_project_scoped_markdown(
        runtime=runtime,
        task_name=task_name,
        section_name=section_name,
        content=content,
        subfolder_name=subfolder_name,
        tool_call_id=tool_call_id,
    )
    if project_scoped is not None:
        return project_scoped

    thread_data = (runtime.state or {}).get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    workspace_root = _proposal_workspace_root(runtime)
    task_dir_name, default_subfolder = _project_scope(workspace_root, runtime, task_name)
    subfolder = _safe_relative_dir(subfolder_name or default_subfolder)
    filename = _ensure_markdown_filename(section_name)

    workspace_file = (workspace_root / task_dir_name / subfolder / filename).resolve()
    try:
        workspace_file.relative_to(workspace_root)
    except ValueError:
        return Command(
            update={"messages": [ToolMessage("Error: invalid proposal workspace path", tool_call_id=tool_call_id)]}
        )

    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text(content, encoding="utf-8")

    if not outputs_path:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Saved Markdown draft to workspace: {workspace_file}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    outputs_root = Path(outputs_path).resolve()
    output_file = (outputs_root / "proposal_drafts" / task_dir_name / subfolder / filename).resolve()
    try:
        output_file.relative_to(outputs_root)
    except ValueError:
        return Command(
            update={"messages": [ToolMessage("Error: invalid artifact output path", tool_call_id=tool_call_id)]}
        )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(workspace_file, output_file)

    artifact_parts = [task_dir_name, *subfolder.parts, filename]
    artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/proposal_drafts/{'/'.join(artifact_parts)}"
    return Command(
        update={
            "artifacts": [artifact_path],
            "messages": [
                ToolMessage(
                    f"Saved Markdown draft to {workspace_file} and presented {artifact_path}",
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )
