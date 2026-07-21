"""Project workspace API for government project declaration workflows."""

from __future__ import annotations

import asyncio
import io
import mimetypes
import os
import re
import shutil
import subprocess
import webbrowser
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.gateway.deps import get_thread_store
from app.gateway.docx_export import build_markdown_docx, docx_media_type
from deerflow.config.paths import VIRTUAL_PATH_PREFIX, get_paths
from deerflow.government_project_workspace import government_project_workspace_root
from deerflow.knowledge.export_images import (
    ExportEvidenceDocument,
    ExportImageSelectionModelError,
    NoRelevantImageEvidenceError,
    NoVerifiedImageEvidenceError,
    enrich_export_documents_with_images,
)
from deerflow.runtime.user_context import get_effective_user_id, strict_user_context_enabled
from deerflow.uploads.manager import (
    UnsafeUploadPathError,
    claim_unique_filename,
    normalize_filename,
    open_upload_file_no_symlink,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PROJECT_META_FILE = ".project.json"
_DEFAULT_PROJECT_TYPE = "government-project-declaration"
_PROJECT_UPLOAD_CHUNK_SIZE = 8192
_PROJECT_MAX_UPLOAD_FILES = 20
_PROJECT_MAX_FILE_SIZE = 80 * 1024 * 1024
_PROJECT_MAX_TOTAL_UPLOAD_SIZE = 200 * 1024 * 1024
_PROJECT_EXPORT_ORDER_TEMPLATE: tuple[tuple[str, ...], ...] = (
    ("项目标题", "项目名称", "标题"),
    ("项目背景与立项", "立项目的", "项目背景"),
    ("国内外研究现状", "研究现状"),
    ("研究目标与研究内容", "研究目标", "研究内容"),
    ("研究方案与技术路线", "技术路线", "研究方案"),
    ("关键科学问题", "科学问题"),
    ("特色与创新之处", "创新之处", "创新点", "项目特色"),
    ("预期研究成果", "考核指标", "预期成果"),
    ("研究进度安排", "进度安排", "实施计划"),
    ("经费预算", "预算"),
)


_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None)
    type: str = Field(default=_DEFAULT_PROJECT_TYPE, max_length=80)
    metadata: dict[str, object] = Field(default_factory=dict)


class ProjectPatchRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    metadata: dict[str, object] | None = Field(default=None)


class ProjectResponse(BaseModel):
    project_id: str
    name: str
    type: str
    status: str = "active"
    root_path: str
    created_at: str
    updated_at: str
    metadata: dict[str, object] = Field(default_factory=dict)


class ProjectDirectoryResponse(BaseModel):
    project_id: str
    root_path: str
    default_root_path: str
    exists: bool


class ProjectDirectoryUpdateRequest(BaseModel):
    root_path: str | None = Field(default=None, max_length=4096)
    create: bool = True


class ProjectDirectoryOpenResponse(BaseModel):
    project_id: str
    root_path: str
    opened: bool = True


class ProjectDirectorySelectResponse(BaseModel):
    project_id: str
    root_path: str | None = None
    selected: bool = False


class ProjectFileNode(BaseModel):
    id: str
    name: str
    path: str
    read_path: str
    kind: Literal["file"] = "file"
    category: Literal["draft", "input", "output", "version", "other"]
    source: Literal["project", "thread"]
    size: int
    updated_at: str
    mime_type: str | None = None
    thread_id: str | None = None
    artifact_url: str | None = None


class ProjectFilesResponse(BaseModel):
    project_id: str
    files: list[ProjectFileNode]


class ProjectSummaryResponse(BaseModel):
    project_id: str
    threads_count: int = 0
    drafts_count: int = 0
    inputs_count: int = 0
    outputs_count: int = 0
    versions_count: int = 0
    files_count: int = 0
    total_size: int = 0
    updated_at: str
    latest_file_at: str | None = None


class ProjectFileReadResponse(BaseModel):
    project_id: str
    path: str
    source: Literal["project", "thread"]
    content: str
    mime_type: str | None = None
    truncated: bool = False


class ProjectFileWriteRequest(BaseModel):
    path: str
    content: str = ""
    source: Literal["project", "thread"] = "project"
    thread_id: str | None = None


class ProjectFileExportItem(BaseModel):
    path: str
    name: str | None = None
    source: Literal["project", "thread"] = "project"
    thread_id: str | None = None


class ProjectFileExportRequest(BaseModel):
    files: list[ProjectFileExportItem] = Field(min_length=1, max_length=80)
    mode: Literal["merged", "separate"] = "merged"
    title: str | None = Field(default=None, max_length=120)
    include_images: bool = False
    applicant_id: str = Field(default="default", min_length=1, max_length=128)
    model_name: str | None = Field(default=None, max_length=120)


class ProjectFileUploadResponse(BaseModel):
    success: bool
    files: list[ProjectFileNode]
    message: str
    skipped_files: list[str] = Field(default_factory=list)


class ProjectDraftFile(BaseModel):
    task_name: str
    section_name: str
    file_path: str
    updated_at: str
    size: int


class ProjectDraftListResponse(BaseModel):
    project_id: str
    root_path: str
    files: list[ProjectDraftFile]


class ProjectDraftReadResponse(BaseModel):
    project_id: str
    section_name: str
    file_path: str
    content: str


class ProjectDraftSaveRequest(BaseModel):
    content: str = ""


class ProjectDraftVersion(BaseModel):
    version_id: str
    section_name: str
    file_path: str
    created_at: str
    size: int


class ProjectDraftVersionListResponse(BaseModel):
    project_id: str
    section_name: str
    versions: list[ProjectDraftVersion]


class ProjectDraftVersionCreateResponse(BaseModel):
    project_id: str
    version: ProjectDraftVersion


class ProjectDraftVersionReadResponse(BaseModel):
    project_id: str
    section_name: str
    version_id: str
    file_path: str
    content: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _projects_root() -> Path:
    root = get_paths().user_projects_dir(get_effective_user_id()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_project_id(project_id: str) -> str:
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id.")
    return project_id


def _project_dir(project_id: str) -> Path:
    root = _projects_root()
    safe_id = _validate_project_id(project_id)
    path = (root / safe_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid project path.") from exc
    return path


def _project_meta_path(project_id: str) -> Path:
    return _project_dir(project_id) / _PROJECT_META_FILE


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_project_root(project_id: str) -> Path:
    return _project_dir(project_id).resolve()


def _default_workspace_root() -> Path:
    if strict_user_context_enabled():
        root = get_paths().user_projects_dir(get_effective_user_id()).resolve()
    else:
        root = government_project_workspace_root().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_external_project_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if strict_user_context_enabled():
        user_root = get_paths().user_dir(get_effective_user_id()).resolve()
        try:
            resolved.relative_to(user_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="Project directory must stay inside the current user's storage root.",
            ) from exc
        return resolved
    code_root = _repo_root().resolve()
    try:
        resolved.relative_to(code_root)
    except ValueError:
        return resolved
    raise HTTPException(
        status_code=400,
        detail="Project directory must be outside the source-code tree.",
    )


def _resolve_project_root_path(
    value: object,
    project_id: str,
    *,
    use_workspace_default: bool = False,
) -> Path:
    if isinstance(value, str) and value.strip():
        path = Path(value.strip())
    elif use_workspace_default:
        path = _default_workspace_root()
    else:
        path = _default_project_root(project_id)
    resolved = _ensure_external_project_root(path)
    if resolved.exists() and not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Project directory path is not a directory.")
    return resolved


def _project_root_path(project: ProjectResponse | str) -> Path:
    if isinstance(project, ProjectResponse):
        return Path(project.root_path).resolve()
    return Path(_read_project(project).root_path).resolve()


def _ensure_project_dirs(project_dir: Path) -> None:
    for name in ("inputs", "drafts", "outputs", "versions", "files"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)


def _read_project(project_id: str) -> ProjectResponse:
    project_dir = _project_dir(project_id)
    meta_path = project_dir / _PROJECT_META_FILE
    if not project_dir.exists() or not meta_path.is_file():
        raise HTTPException(status_code=404, detail="Project not found.")

    try:
        import json

        raw = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - request boundary
        raise HTTPException(status_code=500, detail="Project metadata is not readable.") from exc

    if not isinstance(raw, dict):
        raise HTTPException(status_code=500, detail="Project metadata is invalid.")

    owner_id = raw.get("owner_id")
    if owner_id is not None and str(owner_id) != get_effective_user_id():
        raise HTTPException(status_code=404, detail="Project not found.")

    project_root = _resolve_project_root_path(raw.get("root_path"), project_id)
    project_root.mkdir(parents=True, exist_ok=True)
    _ensure_project_dirs(project_root)

    return ProjectResponse(
        project_id=str(raw.get("project_id") or project_id),
        name=str(raw.get("name") or project_id),
        type=str(raw.get("type") or _DEFAULT_PROJECT_TYPE),
        status=str(raw.get("status") or "active"),
        root_path=str(project_root),
        created_at=str(raw.get("created_at") or ""),
        updated_at=str(raw.get("updated_at") or ""),
        metadata=dict(raw.get("metadata") or {}),
    )


def _write_project(project: ProjectResponse, *, owner_id: str | None = None) -> ProjectResponse:
    project_dir = _project_dir(project.project_id)
    project_dir.mkdir(parents=True, exist_ok=True)
    project_root = _resolve_project_root_path(project.root_path, project.project_id)
    project_root.mkdir(parents=True, exist_ok=True)
    _ensure_project_dirs(project_root)
    data = project.model_dump()
    data["root_path"] = str(project_root)
    if owner_id:
        data["owner_id"] = owner_id

    import json

    (project_dir / _PROJECT_META_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return _read_project(project.project_id)


def _safe_relative_file_path(value: str) -> Path:
    raw = value.strip().replace("\\", "/")
    parts = [part for part in raw.split("/") if part]
    if not parts or any(part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    return Path(*parts)


def _project_file_path(project: ProjectResponse | str, relative_path: str) -> Path:
    root = _project_root_path(project)
    relative = _safe_relative_file_path(relative_path)
    if relative.as_posix() == _PROJECT_META_FILE or any(part.startswith(".") for part in relative.parts):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file path.") from exc
    return path


def _draft_relative_path(section_name: str) -> Path:
    path = _safe_relative_file_path(section_name)
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    return Path("drafts") / path


def _section_name_from_draft_relative(relative: Path) -> str:
    return relative.relative_to("drafts").with_suffix("").as_posix()


def _version_dir(project: ProjectResponse | str, section_name: str) -> tuple[Path, str]:
    draft_relative = _draft_relative_path(section_name)
    section = _section_name_from_draft_relative(draft_relative)
    root = _project_root_path(project)
    version_dir = (root / "versions" / Path(section)).resolve()
    try:
        version_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    return version_dir, section


def _version_path(project: ProjectResponse | str, section_name: str, version_id: str) -> tuple[Path, str, str]:
    safe_version_id = _safe_relative_file_path(version_id).as_posix()
    if "/" in safe_version_id or "\\" in safe_version_id:
        raise HTTPException(status_code=400, detail="Invalid version_id.")
    version_dir, section = _version_dir(project, section_name)
    root = _project_root_path(project)
    path = (version_dir / f"{safe_version_id}.md").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    return path, section, safe_version_id


def _category_for_project_path(relative_path: Path) -> Literal["draft", "input", "output", "version", "other"]:
    first = relative_path.parts[0] if relative_path.parts else ""
    if first == "drafts":
        return "draft"
    if first == "inputs":
        return "input"
    if first == "outputs":
        return "output"
    if first == "versions":
        return "version"
    return "other"


def _iso_from_mtime(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _version_item(project: ProjectResponse | str, path: Path, section_name: str) -> ProjectDraftVersion:
    root = _project_root_path(project)
    return ProjectDraftVersion(
        version_id=path.stem,
        section_name=section_name,
        file_path=path.relative_to(root).as_posix(),
        created_at=_iso_from_mtime(path),
        size=path.stat().st_size,
    )


def _project_file_node(project_id: str, root: Path, path: Path) -> ProjectFileNode:
    relative = path.relative_to(root)
    rel_posix = relative.as_posix()
    mime_type, _ = mimetypes.guess_type(path.name)
    return ProjectFileNode(
        id=f"project:{rel_posix}",
        name=path.name,
        path=rel_posix,
        read_path=rel_posix,
        category=_category_for_project_path(relative),
        source="project",
        size=path.stat().st_size,
        updated_at=_iso_from_mtime(path),
        mime_type=mime_type,
    )


def _thread_output_node(thread_id: str, outputs_root: Path, path: Path) -> ProjectFileNode:
    relative = path.relative_to(outputs_root)
    rel_posix = relative.as_posix()
    mime_type, _ = mimetypes.guess_type(path.name)
    artifact_path = f"{VIRTUAL_PATH_PREFIX}/outputs/{rel_posix}"
    return ProjectFileNode(
        id=f"thread:{thread_id}:{rel_posix}",
        name=path.name,
        path=f"threads/{thread_id}/outputs/{rel_posix}",
        read_path=rel_posix,
        category="output",
        source="thread",
        size=path.stat().st_size,
        updated_at=_iso_from_mtime(path),
        mime_type=mime_type,
        thread_id=thread_id,
        artifact_url=f"/api/threads/{thread_id}/artifacts/{quote(artifact_path.lstrip('/'), safe='/')}",
    )


def _is_project_draft_artifact(project_id: str, outputs_root: Path, path: Path) -> bool:
    relative = path.relative_to(outputs_root)
    parts = relative.parts
    return len(parts) >= 4 and parts[0] == "projects" and parts[1] == project_id and parts[2] == "drafts"


def _is_listable_project_file(project_root: Path, path: Path) -> bool:
    if not path.is_file():
        return False
    relative = path.relative_to(project_root)
    if relative.as_posix() == _PROJECT_META_FILE:
        return False
    return not any(part.startswith(".") for part in relative.parts)


async def _thread_output_files(project_id: str, request: Request) -> list[ProjectFileNode]:
    nodes: list[ProjectFileNode] = []
    paths = get_paths()
    user_id = get_effective_user_id()
    for thread in await _project_threads(project_id, request):
        thread_id = thread.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id:
            continue
        outputs_root = paths.sandbox_outputs_dir(thread_id, user_id=user_id)
        if not outputs_root.exists():
            continue
        for path in outputs_root.rglob("*"):
            if path.is_file() and not _is_project_draft_artifact(project_id, outputs_root, path):
                nodes.append(_thread_output_node(thread_id, outputs_root, path))
    return nodes


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="File is not UTF-8 text.") from exc


def _export_source_path(project: ProjectResponse | str, item: ProjectFileExportItem) -> Path:
    if item.source == "thread":
        if not item.thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required for thread files.")
        outputs_root = get_paths().sandbox_outputs_dir(item.thread_id, user_id=get_effective_user_id()).resolve()
        path = (outputs_root / _safe_relative_file_path(item.path)).resolve()
        try:
            path.relative_to(outputs_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
        return path
    return _project_file_path(project, item.path)


def _export_title(item: ProjectFileExportItem, path: Path) -> str:
    source_name = (item.name or path.name).strip()
    return Path(source_name).stem or path.stem


def _export_sort_key(item: ProjectFileExportItem, path: Path, content: str) -> tuple[int, str]:
    title = _export_title(item, path)
    haystack = f"{title}\n{item.path}\n{content[:1200]}"
    for index, keywords in enumerate(_PROJECT_EXPORT_ORDER_TEMPLATE):
        if any(keyword in haystack for keyword in keywords):
            return (index, title)
    return (len(_PROJECT_EXPORT_ORDER_TEMPLATE), title)


def _strip_markdown_title_markup(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)
    text = re.sub(r"~~([^~\n]+)~~", r"\1", text)
    return text.strip()


def _starts_with_markdown_heading(content: str) -> bool:
    for line in content.splitlines():
        if not line.strip():
            continue
        return _MARKDOWN_HEADING_RE.match(line) is not None
    return False


def _drop_repeated_merged_preamble(title: str, content: str) -> str:
    lines = content.splitlines()
    first_heading_index: int | None = None
    first_heading: re.Match[str] | None = None
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        first_heading = _MARKDOWN_HEADING_RE.match(line)
        first_heading_index = index
        break
    if first_heading_index is None or first_heading is None or first_heading.group(1) != "#":
        return content.strip()

    for line in lines[first_heading_index + 1 : first_heading_index + 8]:
        if not line.strip():
            continue
        heading = _MARKDOWN_HEADING_RE.match(line)
        if heading is None:
            break
        if _strip_markdown_title_markup(heading.group(2)) == title:
            return "\n".join(lines[first_heading_index + 1 :]).lstrip()
    return content.strip()


def _merged_export_section(title: str, content: str) -> str:
    section = _drop_repeated_merged_preamble(title, content)
    if not section:
        return f"## {title}"
    if _starts_with_markdown_heading(section):
        return section
    return f"## {title}\n\n{section}"


def _safe_export_filename(name: str, suffix: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" ._")
    return f"{cleaned or 'export'}{suffix}"


def _touch_project(project: ProjectResponse) -> ProjectResponse:
    updated = ProjectResponse(**{**project.model_dump(), "updated_at": _now_iso()})
    return _write_project(updated, owner_id=get_effective_user_id())


async def _project_threads(project_id: str, request: Request) -> list[dict[str, object]]:
    try:
        thread_store = get_thread_store(request)
        return await thread_store.search(
            metadata={"project_id": project_id},
            limit=500,
            offset=0,
            user_id=get_effective_user_id(),
        )
    except Exception:
        return []


def _project_upload_dir(
    project: ProjectResponse | str,
    category: Literal["inputs", "outputs", "drafts", "files"],
) -> Path:
    project_root = _project_root_path(project)
    folder = {
        "inputs": "inputs",
        "outputs": "outputs",
        "drafts": "drafts",
        "files": "files",
    }[category]
    target_dir = (project_root / folder).resolve()
    try:
        target_dir.relative_to(project_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid upload category.") from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


async def _write_project_upload_file(
    file: UploadFile,
    *,
    target_dir: Path,
    display_filename: str,
    total_size: int,
) -> tuple[Path, int, int]:
    file_size = 0
    file_path, fh = open_upload_file_no_symlink(target_dir, display_filename)
    try:
        while chunk := await file.read(_PROJECT_UPLOAD_CHUNK_SIZE):
            file_size += len(chunk)
            total_size += len(chunk)
            if file_size > _PROJECT_MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large: {display_filename}")
            if total_size > _PROJECT_MAX_TOTAL_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail="Total upload size too large")
            fh.write(chunk)
    except Exception:
        fh.close()
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        raise
    else:
        fh.close()
    return file_path, file_size, total_size


@router.get("", response_model=list[ProjectResponse], summary="List Projects")
async def list_projects() -> list[ProjectResponse]:
    owner_id = get_effective_user_id()
    projects: list[ProjectResponse] = []
    for candidate in _projects_root().iterdir():
        if not candidate.is_dir():
            continue
        meta_path = candidate / _PROJECT_META_FILE
        if not meta_path.is_file():
            continue
        try:
            import json

            raw = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if raw.get("owner_id") not in (None, owner_id):
            continue
        try:
            projects.append(_read_project(candidate.name))
        except HTTPException:
            continue
    projects.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return projects


@router.post("", response_model=ProjectResponse, summary="Create Project")
async def create_project(body: ProjectCreateRequest) -> ProjectResponse:
    project_id = _validate_project_id(body.project_id or uuid4().hex)
    project_dir = _project_dir(project_id)
    if (project_dir / _PROJECT_META_FILE).exists():
        raise HTTPException(status_code=409, detail="Project already exists.")

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    now = _now_iso()
    project = ProjectResponse(
        project_id=project_id,
        name=name,
        type=body.type.strip() or _DEFAULT_PROJECT_TYPE,
        status="active",
        root_path=str(project_dir),
        created_at=now,
        updated_at=now,
        metadata=body.metadata,
    )
    return _write_project(project, owner_id=get_effective_user_id())


@router.get("/{project_id}", response_model=ProjectResponse, summary="Get Project")
async def get_project(project_id: str) -> ProjectResponse:
    return _read_project(project_id)


@router.patch("/{project_id}", response_model=ProjectResponse, summary="Update Project")
async def update_project(project_id: str, body: ProjectPatchRequest) -> ProjectResponse:
    project = _read_project(project_id)
    metadata = dict(project.metadata)
    if body.metadata:
        metadata.update(body.metadata)
    updated = ProjectResponse(
        **{
            **project.model_dump(),
            "name": body.name.strip() if isinstance(body.name, str) and body.name.strip() else project.name,
            "status": body.status.strip() if isinstance(body.status, str) and body.status.strip() else project.status,
            "metadata": metadata,
            "updated_at": _now_iso(),
        }
    )
    return _write_project(updated, owner_id=get_effective_user_id())


def _directory_response(project: ProjectResponse) -> ProjectDirectoryResponse:
    root = Path(project.root_path).resolve()
    return ProjectDirectoryResponse(
        project_id=project.project_id,
        root_path=str(root),
        default_root_path=str(_default_workspace_root()),
        exists=root.is_dir(),
    )


def _open_directory(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if webbrowser.open(path.as_uri()):
        return
    raise OSError(f"Could not open directory: {path}")


def _select_project_directory(initial_dir: Path) -> Path | None:
    if os.name == "nt":
        script = rf"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '选择项目目录'
$dialog.ShowNewFolderButton = $true
$initial = '{str(initial_dir).replace("'", "''")}'
if ([System.IO.Directory]::Exists($initial)) {{
    $dialog.SelectedPath = $initial
}}
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.SelectedPath
    exit 0
}}
exit 2
"""
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if completed.returncode == 2:
            return None
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "Directory selection failed.").strip()
            raise OSError(message)
        selected = completed.stdout.strip().splitlines()
        return Path(selected[-1]).expanduser().resolve() if selected else None

    try:
        import tkinter
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001 - optional desktop integration
        raise OSError("Directory selection dialog is not available on this platform.") from exc

    root = tkinter.Tk()
    root.withdraw()
    try:
        selected = filedialog.askdirectory(
            title="选择项目目录",
            initialdir=str(initial_dir) if initial_dir.is_dir() else str(_default_workspace_root()),
            mustexist=False,
        )
    finally:
        root.destroy()
    return Path(selected).expanduser().resolve() if selected else None


@router.get(
    "/{project_id}/directory",
    response_model=ProjectDirectoryResponse,
    summary="Get Project Directory",
)
async def get_project_directory(project_id: str) -> ProjectDirectoryResponse:
    return _directory_response(_read_project(project_id))


@router.put(
    "/{project_id}/directory",
    response_model=ProjectDirectoryResponse,
    summary="Update Project Directory",
)
async def update_project_directory(project_id: str, body: ProjectDirectoryUpdateRequest) -> ProjectDirectoryResponse:
    project = _read_project(project_id)
    target = _resolve_project_root_path(body.root_path, project_id, use_workspace_default=True)
    if target.exists() and not target.is_dir():
        raise HTTPException(status_code=400, detail="Project directory path is not a directory.")
    if body.create:
        target.mkdir(parents=True, exist_ok=True)
        _ensure_project_dirs(target)
    elif not target.exists():
        raise HTTPException(status_code=404, detail="Project directory does not exist.")

    updated = ProjectResponse(**{**project.model_dump(), "root_path": str(target), "updated_at": _now_iso()})
    return _directory_response(_write_project(updated, owner_id=get_effective_user_id()))


@router.post(
    "/{project_id}/directory/select",
    response_model=ProjectDirectorySelectResponse,
    summary="Select Project Directory",
)
async def select_project_directory(project_id: str) -> ProjectDirectorySelectResponse:
    project = _read_project(project_id)
    try:
        selected = await asyncio.to_thread(_select_project_directory, Path(project.root_path).resolve())
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    if selected is None:
        return ProjectDirectorySelectResponse(project_id=project.project_id, selected=False)
    selected_root = _resolve_project_root_path(str(selected), project_id)
    return ProjectDirectorySelectResponse(project_id=project.project_id, root_path=str(selected_root), selected=True)


@router.post(
    "/{project_id}/directory/open",
    response_model=ProjectDirectoryOpenResponse,
    summary="Open Project Directory",
)
async def open_project_directory(project_id: str) -> ProjectDirectoryOpenResponse:
    project = _read_project(project_id)
    root = Path(project.root_path).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _ensure_project_dirs(root)
    try:
        _open_directory(root)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProjectDirectoryOpenResponse(project_id=project.project_id, root_path=str(root))


@router.delete("/{project_id}", status_code=204, summary="Delete Project")
async def delete_project(project_id: str) -> None:
    _read_project(project_id)
    project_dir = _project_dir(project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found.")
    shutil.rmtree(project_dir)


@router.get("/{project_id}/files", response_model=ProjectFilesResponse, summary="List Project Files")
async def list_project_files(project_id: str, request: Request) -> ProjectFilesResponse:
    project = _read_project(project_id)
    project_root = Path(project.root_path).resolve()
    nodes = [_project_file_node(project_id, project_root, path) for path in project_root.rglob("*") if _is_listable_project_file(project_root, path)]
    nodes.extend(await _thread_output_files(project_id, request))
    nodes.sort(key=lambda item: (item.category, item.path))
    return ProjectFilesResponse(project_id=project_id, files=nodes)


@router.get("/{project_id}/summary", response_model=ProjectSummaryResponse, summary="Get Project Summary")
async def get_project_summary(project_id: str, request: Request) -> ProjectSummaryResponse:
    project = _read_project(project_id)
    project_root = Path(project.root_path).resolve()
    local_nodes = [_project_file_node(project_id, project_root, path) for path in project_root.rglob("*") if _is_listable_project_file(project_root, path)]
    thread_output_nodes = await _thread_output_files(project_id, request)
    nodes = [*local_nodes, *thread_output_nodes]
    latest_file_at = max((node.updated_at for node in nodes), default=None)
    return ProjectSummaryResponse(
        project_id=project_id,
        threads_count=len(await _project_threads(project_id, request)),
        drafts_count=sum(1 for node in nodes if node.category == "draft"),
        inputs_count=sum(1 for node in nodes if node.category == "input"),
        outputs_count=sum(1 for node in nodes if node.category == "output"),
        versions_count=sum(1 for node in nodes if node.category == "version"),
        files_count=len(nodes),
        total_size=sum(node.size for node in nodes),
        updated_at=project.updated_at,
        latest_file_at=latest_file_at,
    )


@router.get("/{project_id}/files/read", response_model=ProjectFileReadResponse, summary="Read Project File")
async def read_project_file(
    project_id: str,
    path: str = Query(...),
    source: Literal["project", "thread"] = Query(default="project"),
    thread_id: str | None = Query(default=None),
) -> ProjectFileReadResponse:
    _read_project(project_id)
    if source == "thread":
        if not thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required for thread files.")
        outputs_root = get_paths().sandbox_outputs_dir(thread_id, user_id=get_effective_user_id()).resolve()
        file_path = (outputs_root / _safe_relative_file_path(path)).resolve()
        try:
            file_path.relative_to(outputs_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
    else:
        file_path = _project_file_path(project_id, path)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    mime_type, _ = mimetypes.guess_type(file_path.name)
    return ProjectFileReadResponse(
        project_id=project_id,
        path=path,
        source=source,
        content=_read_text_file(file_path),
        mime_type=mime_type,
    )


@router.get("/{project_id}/files/download", summary="Download Project File")
async def download_project_file(
    project_id: str,
    path: str = Query(...),
    source: Literal["project", "thread"] = Query(default="project"),
    thread_id: str | None = Query(default=None),
) -> FileResponse:
    _read_project(project_id)
    if source == "thread":
        if not thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required for thread files.")
        outputs_root = get_paths().sandbox_outputs_dir(thread_id, user_id=get_effective_user_id()).resolve()
        file_path = (outputs_root / _safe_relative_file_path(path)).resolve()
        try:
            file_path.relative_to(outputs_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
    else:
        file_path = _project_file_path(project_id, path)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    mime_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type=mime_type or "application/octet-stream",
    )


@router.post("/{project_id}/files/upload", response_model=ProjectFileUploadResponse, summary="Upload Project Files")
async def upload_project_files(
    project_id: str,
    files: list[UploadFile] = File(...),
    category: Literal["inputs", "outputs", "drafts", "files"] = Query(default="inputs"),
) -> ProjectFileUploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > _PROJECT_MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files: maximum is {_PROJECT_MAX_UPLOAD_FILES}.")

    project = _read_project(project_id)
    project_root = Path(project.root_path).resolve()
    target_dir = _project_upload_dir(project, category)
    seen = {path.name for path in target_dir.iterdir() if path.is_file()}
    uploaded: list[ProjectFileNode] = []
    skipped_files: list[str] = []
    written_paths: list[Path] = []
    total_size = 0

    for file in files:
        if not file.filename:
            continue
        try:
            original_filename = normalize_filename(file.filename)
            safe_filename = claim_unique_filename(original_filename, seen)
            file_path, _file_size, total_size = await _write_project_upload_file(
                file,
                target_dir=target_dir,
                display_filename=safe_filename,
                total_size=total_size,
            )
            written_paths.append(file_path)
            uploaded.append(_project_file_node(project_id, project_root, file_path))
        except ValueError:
            skipped_files.append(file.filename)
            continue
        except UnsafeUploadPathError:
            skipped_files.append(file.filename)
            continue
        except HTTPException:
            for path in written_paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            raise
        except Exception as exc:  # noqa: BLE001 - request boundary
            for path in written_paths:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {exc}") from exc

    if not uploaded and skipped_files:
        raise HTTPException(status_code=400, detail="No safe files were uploaded.")
    if uploaded:
        _touch_project(project)
    message = f"Uploaded {len(uploaded)} project file(s)."
    if skipped_files:
        message += f" Skipped {len(skipped_files)} unsafe file(s)."
    return ProjectFileUploadResponse(
        success=not skipped_files,
        files=uploaded,
        message=message,
        skipped_files=skipped_files,
    )


@router.put("/{project_id}/files/write", response_model=ProjectFileNode, summary="Write Project File")
async def write_project_file(project_id: str, body: ProjectFileWriteRequest) -> ProjectFileNode:
    project = _read_project(project_id)
    if body.source == "thread":
        if not body.thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required for thread files.")
        outputs_root = get_paths().sandbox_outputs_dir(body.thread_id, user_id=get_effective_user_id()).resolve()
        path = (outputs_root / _safe_relative_file_path(body.path)).resolve()
        try:
            path.relative_to(outputs_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body.content, encoding="utf-8")
        _touch_project(project)
        return _thread_output_node(body.thread_id, outputs_root, path)

    project_root = Path(project.root_path).resolve()
    path = _project_file_path(project, body.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    _touch_project(project)
    return _project_file_node(project_id, project_root, path)


@router.post("/{project_id}/files/export-docx", summary="Export Project Files as Word")
async def export_project_files_docx(project_id: str, body: ProjectFileExportRequest) -> Response:
    project = _read_project(project_id)
    entries = []
    for item in body.files:
        path = _export_source_path(project, item)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {item.path}")
        content = _read_text_file(path)
        entries.append(
            {
                "item": item,
                "path": path,
                "title": _export_title(item, path),
                "content": content,
                "sort_key": _export_sort_key(item, path, content),
            }
        )

    evidence_count = 0
    if body.include_images:
        try:
            enrichment = await enrich_export_documents_with_images(
                [ExportEvidenceDocument(title=str(entry["title"]), content=str(entry["content"])) for entry in entries],
                applicant_id=body.applicant_id,
                model_name=body.model_name,
                user_id=get_effective_user_id(),
            )
        except NoVerifiedImageEvidenceError as exc:
            raise HTTPException(
                status_code=409,
                detail="当前知识库没有已人工确认的图片证据，请先在知识库确认相关图片后再导出。",
            ) from exc
        except NoRelevantImageEvidenceError as exc:
            raise HTTPException(
                status_code=409,
                detail="智能体未找到与所选文档直接相关的已确认图片，请调整文档内容或知识库证据后重试。",
            ) from exc
        except ExportImageSelectionModelError as exc:
            raise HTTPException(status_code=502, detail=f"智能匹配导出图片失败：{exc}") from exc
        if len(enrichment.markdowns) != len(entries):
            raise HTTPException(status_code=500, detail="智能插图结果与导出文件数量不一致。")
        for entry, enriched_markdown in zip(entries, enrichment.markdowns, strict=True):
            entry["content"] = enriched_markdown
        evidence_count = enrichment.evidence_count

    export_title = (body.title or project.name or "项目文件导出").strip()
    if body.mode == "merged":
        entries.sort(key=lambda entry: entry["sort_key"])
        merged = "\n\n".join(_merged_export_section(str(entry["title"]), str(entry["content"])) for entry in entries)
        data = build_markdown_docx(export_title, merged, include_title=True)
        filename = quote(_safe_export_filename(export_title, ".docx"))
        return Response(
            content=data,
            media_type=docx_media_type(),
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
                "X-Project-Name": quote(project.name),
                "X-Embedded-Evidence-Count": str(evidence_count),
            },
        )

    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, entry in enumerate(entries, start=1):
            title = str(entry["title"])
            name = _safe_export_filename(f"{index:02d}-{title}", ".docx")
            while name in used_names:
                name = _safe_export_filename(f"{index:02d}-{title}-{len(used_names) + 1}", ".docx")
            used_names.add(name)
            archive.writestr(
                name,
                build_markdown_docx(
                    title,
                    str(entry["content"]),
                    base_dir=entry["path"].parent,
                    include_title=not _starts_with_markdown_heading(str(entry["content"])),
                ),
            )

    filename = quote(_safe_export_filename(export_title, ".zip"))
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Project-Name": quote(project.name),
            "X-Embedded-Evidence-Count": str(evidence_count),
        },
    )


@router.delete("/{project_id}/files", status_code=204, summary="Delete Project File")
async def delete_project_file(
    project_id: str,
    path: str = Query(...),
    source: Literal["project", "thread"] = Query(default="project"),
    thread_id: str | None = Query(default=None),
) -> None:
    project = _read_project(project_id)
    if source == "thread":
        if not thread_id:
            raise HTTPException(status_code=400, detail="thread_id is required for thread files.")
        outputs_root = get_paths().sandbox_outputs_dir(thread_id, user_id=get_effective_user_id()).resolve()
        file_path = (outputs_root / _safe_relative_file_path(path)).resolve()
        try:
            file_path.relative_to(outputs_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid file path.") from exc
    else:
        file_path = _project_file_path(project, path)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    file_path.unlink()
    _touch_project(project)


@router.get("/{project_id}/drafts", response_model=ProjectDraftListResponse, summary="List Project Drafts")
async def list_project_drafts(project_id: str) -> ProjectDraftListResponse:
    project = _read_project(project_id)
    drafts_root = Path(project.root_path).resolve() / "drafts"
    drafts_root.mkdir(parents=True, exist_ok=True)
    files: list[ProjectDraftFile] = []
    for path in drafts_root.rglob("*.md"):
        if not path.is_file() or any(part.startswith(".") for part in path.relative_to(drafts_root).parts):
            continue
        relative = path.relative_to(drafts_root).with_suffix("").as_posix()
        files.append(
            ProjectDraftFile(
                task_name=project.name,
                section_name=relative,
                file_path=path.relative_to(drafts_root).as_posix(),
                updated_at=_iso_from_mtime(path),
                size=path.stat().st_size,
            )
        )
    files.sort(key=lambda item: item.section_name)
    return ProjectDraftListResponse(project_id=project_id, root_path=str(drafts_root), files=files)


@router.get("/{project_id}/drafts/download/{section_name:path}", summary="Download Project Draft")
async def download_project_draft(project_id: str, section_name: str) -> Response:
    project = _read_project(project_id)
    relative = _draft_relative_path(section_name)
    path = _project_file_path(project, relative.as_posix())
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Draft not found.")
    filename = quote(path.name)
    return Response(
        content=path.read_bytes(),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "X-Project-Name": quote(project.name)},
    )


@router.get("/{project_id}/drafts/download-docx/{section_name:path}", summary="Download Project Draft as Word")
async def download_project_draft_docx(project_id: str, section_name: str) -> Response:
    project = _read_project(project_id)
    relative = _draft_relative_path(section_name)
    path = _project_file_path(project, relative.as_posix())
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Draft not found.")
    data = build_markdown_docx(path.stem, path.read_text(encoding="utf-8"), base_dir=path.parent)
    filename = quote(f"{path.stem}.docx")
    return Response(
        content=data,
        media_type=docx_media_type(),
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}", "X-Project-Name": quote(project.name)},
    )


@router.get(
    "/{project_id}/draft-versions/{section_name:path}",
    response_model=ProjectDraftVersionListResponse,
    summary="List Project Draft Versions",
)
async def list_project_draft_versions(project_id: str, section_name: str) -> ProjectDraftVersionListResponse:
    project = _read_project(project_id)
    version_dir, section = _version_dir(project, section_name)
    versions = [_version_item(project, path, section) for path in version_dir.glob("*.md") if path.is_file()]
    versions.sort(key=lambda item: item.created_at, reverse=True)
    return ProjectDraftVersionListResponse(
        project_id=project_id,
        section_name=section,
        versions=versions,
    )


@router.post(
    "/{project_id}/draft-versions/{section_name:path}",
    response_model=ProjectDraftVersionCreateResponse,
    summary="Create Project Draft Version",
)
async def create_project_draft_version(project_id: str, section_name: str) -> ProjectDraftVersionCreateResponse:
    project = _read_project(project_id)
    draft_relative = _draft_relative_path(section_name)
    draft_path = _project_file_path(project, draft_relative.as_posix())
    if not draft_path.exists() or not draft_path.is_file():
        raise HTTPException(status_code=404, detail="Draft not found.")
    version_dir, section = _version_dir(project, section_name)
    version_dir.mkdir(parents=True, exist_ok=True)
    version_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    version_path = (version_dir / f"{version_id}.md").resolve()
    root = _project_root_path(project)
    try:
        version_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    version_path.write_text(draft_path.read_text(encoding="utf-8"), encoding="utf-8")
    _touch_project(project)
    return ProjectDraftVersionCreateResponse(
        project_id=project_id,
        version=_version_item(project, version_path, section),
    )


@router.get(
    "/{project_id}/draft-version-content/{section_name:path}",
    response_model=ProjectDraftVersionReadResponse,
    summary="Read Project Draft Version",
)
async def read_project_draft_version(
    project_id: str,
    section_name: str,
    version_id: str,
) -> ProjectDraftVersionReadResponse:
    project = _read_project(project_id)
    path, section, safe_version_id = _version_path(project, section_name, version_id)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Draft version not found.")
    root = _project_root_path(project)
    return ProjectDraftVersionReadResponse(
        project_id=project_id,
        section_name=section,
        version_id=safe_version_id,
        file_path=path.relative_to(root).as_posix(),
        content=path.read_text(encoding="utf-8"),
    )


@router.get("/{project_id}/drafts/{section_name:path}", response_model=ProjectDraftReadResponse, summary="Read Project Draft")
async def read_project_draft(project_id: str, section_name: str) -> ProjectDraftReadResponse:
    project = _read_project(project_id)
    relative = _draft_relative_path(section_name)
    path = _project_file_path(project, relative.as_posix())
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Draft not found.")
    section = _section_name_from_draft_relative(relative)
    return ProjectDraftReadResponse(
        project_id=project_id,
        section_name=section,
        file_path=relative.relative_to("drafts").as_posix(),
        content=path.read_text(encoding="utf-8"),
    )


@router.put("/{project_id}/drafts/{section_name:path}", response_model=ProjectDraftFile, summary="Save Project Draft")
async def save_project_draft(project_id: str, section_name: str, body: ProjectDraftSaveRequest) -> ProjectDraftFile:
    project = _read_project(project_id)
    relative = _draft_relative_path(section_name)
    path = _project_file_path(project, relative.as_posix())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.content, encoding="utf-8")
    updated = ProjectResponse(**{**project.model_dump(), "updated_at": _now_iso()})
    _write_project(updated, owner_id=get_effective_user_id())
    section = _section_name_from_draft_relative(relative)
    return ProjectDraftFile(
        task_name=project.name,
        section_name=section,
        file_path=relative.relative_to("drafts").as_posix(),
        updated_at=_iso_from_mtime(path),
        size=path.stat().st_size,
    )


@router.delete("/{project_id}/drafts/{section_name:path}", status_code=204, summary="Delete Project Draft")
async def delete_project_draft(project_id: str, section_name: str) -> None:
    project = _read_project(project_id)
    relative = _draft_relative_path(section_name)
    path = _project_file_path(project, relative.as_posix())
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Draft not found.")
    path.unlink()
    _touch_project(project)
