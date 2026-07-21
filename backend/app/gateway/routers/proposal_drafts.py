"""Proposal draft Markdown management API."""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.gateway.docx_export import build_markdown_docx, docx_media_type
from deerflow.config.paths import get_paths
from deerflow.runtime.user_context import get_effective_user_id

router = APIRouter(prefix="/api/proposal-drafts", tags=["proposal-drafts"])


class ProposalDraftFile(BaseModel):
    task_name: str
    section_name: str
    file_path: str
    updated_at: str
    size: int


class ProposalDraftListResponse(BaseModel):
    root_path: str
    files: list[ProposalDraftFile]


class ProposalDraftReadResponse(BaseModel):
    task_name: str
    section_name: str
    file_path: str
    content: str


class ProposalDraftSaveRequest(BaseModel):
    content: str = Field(default="")


class ProposalDraftSaveResponse(BaseModel):
    task_name: str
    section_name: str
    file_path: str
    size: int


class ProposalDraftVersion(BaseModel):
    version_id: str
    task_name: str
    section_name: str
    file_path: str
    created_at: str
    size: int


class ProposalDraftVersionCreateResponse(BaseModel):
    version: ProposalDraftVersion


class ProposalDraftVersionListResponse(BaseModel):
    task_name: str
    section_name: str
    versions: list[ProposalDraftVersion]


class ProposalDraftVersionReadResponse(BaseModel):
    task_name: str
    section_name: str
    version_id: str
    file_path: str
    content: str


def _drafts_root() -> Path:
    root = get_paths().user_drafts_dir(get_effective_user_id()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path_part(value: str, field_name: str) -> str:
    part = value.strip()
    if not part or part in {".", ".."} or "/" in part or "\\" in part:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.")
    return part


def _safe_section_path(value: str) -> Path:
    raw = value.strip().replace("\\", "/")
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Invalid section_name.")
    if any(part in {".", ".."} or "/" in part or "\\" in part for part in parts):
        raise HTTPException(status_code=400, detail="Invalid section_name.")

    *folders, section = parts
    filename = section if section.lower().endswith(".md") else f"{section}.md"
    return Path(*folders, filename) if folders else Path(filename)


def _section_name_from_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    parts = relative.parts[1:]
    if not parts:
        return path.stem
    return Path(*parts).with_suffix("").as_posix()


def _resolve_draft_path(task_name: str, section_name: str) -> tuple[Path, Path]:
    root = _drafts_root()
    task = _safe_path_part(task_name, "task_name")
    section_path = _safe_section_path(section_name)
    path = (root / task / section_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid draft path.") from exc
    return root, path


def _resolve_version_dir(task_name: str, section_name: str) -> tuple[Path, Path, str, str]:
    root, draft_path = _resolve_draft_path(task_name, section_name)
    task = draft_path.relative_to(root).parts[0]
    section = _section_name_from_path(root, draft_path)
    version_dir = (root / task / ".history" / Path(section)).resolve()
    try:
        version_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    return root, version_dir, task, section


def _resolve_version_path(task_name: str, section_name: str, version_id: str) -> tuple[Path, Path, str, str, str]:
    root, version_dir, task, section = _resolve_version_dir(task_name, section_name)
    safe_version_id = _safe_path_part(version_id, "version_id")
    path = (version_dir / f"{safe_version_id}.md").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    return root, path, task, section, safe_version_id


def _to_file_item(root: Path, path: Path) -> ProposalDraftFile:
    stat = path.stat()
    relative_path = path.relative_to(root).as_posix()
    return ProposalDraftFile(
        task_name=path.relative_to(root).parts[0],
        section_name=_section_name_from_path(root, path),
        file_path=relative_path,
        updated_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        size=stat.st_size,
    )


def _to_version_item(root: Path, path: Path, task_name: str, section_name: str) -> ProposalDraftVersion:
    stat = path.stat()
    return ProposalDraftVersion(
        version_id=path.stem,
        task_name=task_name,
        section_name=section_name,
        file_path=path.relative_to(root).as_posix(),
        created_at=datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        size=stat.st_size,
    )


def _is_listable_draft(root: Path, path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() != ".md":
        return False
    if path.name.lower() == "readme.md" or path.parent == root:
        return False
    relative_parts = path.relative_to(root).parts
    if not relative_parts:
        return False
    return not any(part.startswith(".") for part in relative_parts)


@router.get("", response_model=ProposalDraftListResponse, summary="List Proposal Drafts")
async def list_proposal_drafts() -> ProposalDraftListResponse:
    """List Markdown drafts in the unified government-project workspace."""
    root = _drafts_root()
    files = [_to_file_item(root, path) for path in root.rglob("*.md") if _is_listable_draft(root, path)]
    files.sort(key=lambda item: (item.task_name, item.section_name))
    return ProposalDraftListResponse(root_path=str(root), files=files)


@router.get(
    "/download/{task_name}/{section_name:path}",
    summary="Download Proposal Draft",
)
async def download_proposal_draft(task_name: str, section_name: str) -> Response:
    """Download a Markdown draft by task and section name."""
    root, path = _resolve_draft_path(task_name, section_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft not found.")
    filename = quote(path.name)
    return Response(
        content=path.read_bytes(),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Proposal-Draft-Path": quote(path.relative_to(root).as_posix()),
        },
    )


@router.get(
    "/download-docx/{task_name}/{section_name:path}",
    summary="Download Proposal Draft as Word",
)
async def download_proposal_draft_docx(task_name: str, section_name: str) -> Response:
    """Download a Markdown draft rendered as a formatted Word document."""
    root, path = _resolve_draft_path(task_name, section_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft not found.")
    data = build_markdown_docx(
        path.stem,
        path.read_text(encoding="utf-8"),
        base_dir=path.parent,
    )
    filename = quote(f"{path.stem}.docx")
    return Response(
        content=data,
        media_type=docx_media_type(),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "X-Proposal-Draft-Path": quote(path.relative_to(root).as_posix()),
        },
    )


@router.get(
    "/versions/{task_name}/{section_name:path}",
    response_model=ProposalDraftVersionListResponse,
    summary="List Proposal Draft Versions",
)
async def list_proposal_draft_versions(
    task_name: str,
    section_name: str,
) -> ProposalDraftVersionListResponse:
    """List saved Markdown snapshots for a draft section."""
    root, version_dir, task, section = _resolve_version_dir(task_name, section_name)
    versions = [
        _to_version_item(root, path, task, section)
        for path in version_dir.glob("*.md")
        if path.is_file()
    ]
    versions.sort(key=lambda item: item.created_at, reverse=True)
    return ProposalDraftVersionListResponse(
        task_name=task,
        section_name=section,
        versions=versions,
    )


@router.post(
    "/versions/{task_name}/{section_name:path}",
    response_model=ProposalDraftVersionCreateResponse,
    summary="Create Proposal Draft Version",
)
async def create_proposal_draft_version(
    task_name: str,
    section_name: str,
) -> ProposalDraftVersionCreateResponse:
    """Save the current Markdown draft as a version snapshot."""
    root, draft_path = _resolve_draft_path(task_name, section_name)
    if not draft_path.exists() or not draft_path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft not found.")
    _, version_dir, task, section = _resolve_version_dir(task_name, section_name)
    version_dir.mkdir(parents=True, exist_ok=True)
    version_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    version_path = (version_dir / f"{version_id}.md").resolve()
    try:
        version_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid version path.") from exc
    version_path.write_text(draft_path.read_text(encoding="utf-8"), encoding="utf-8")
    return ProposalDraftVersionCreateResponse(
        version=_to_version_item(root, version_path, task, section)
    )


@router.get(
    "/version-content/{task_name}/{section_name:path}",
    response_model=ProposalDraftVersionReadResponse,
    summary="Read Proposal Draft Version",
)
async def read_proposal_draft_version(
    task_name: str,
    section_name: str,
    version_id: str,
) -> ProposalDraftVersionReadResponse:
    """Read one saved Markdown snapshot without overwriting the active draft."""
    root, path, task, section, safe_version_id = _resolve_version_path(task_name, section_name, version_id)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft version not found.")
    return ProposalDraftVersionReadResponse(
        task_name=task,
        section_name=section,
        version_id=safe_version_id,
        file_path=path.relative_to(root).as_posix(),
        content=path.read_text(encoding="utf-8"),
    )


@router.get(
    "/{task_name}/{section_name:path}",
    response_model=ProposalDraftReadResponse,
    summary="Read Proposal Draft",
)
async def read_proposal_draft(task_name: str, section_name: str) -> ProposalDraftReadResponse:
    """Read a Markdown draft by task and section name."""
    root, path = _resolve_draft_path(task_name, section_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft not found.")
    return ProposalDraftReadResponse(
        task_name=path.relative_to(root).parts[0],
        section_name=_section_name_from_path(root, path),
        file_path=path.relative_to(root).as_posix(),
        content=path.read_text(encoding="utf-8"),
    )


@router.put(
    "/{task_name}/{section_name:path}",
    response_model=ProposalDraftSaveResponse,
    summary="Save Proposal Draft",
)
async def save_proposal_draft(
    task_name: str,
    section_name: str,
    request: ProposalDraftSaveRequest,
) -> ProposalDraftSaveResponse:
    """Create or update a Markdown draft by task and section name."""
    root, path = _resolve_draft_path(task_name, section_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(request.content, encoding="utf-8")
    return ProposalDraftSaveResponse(
        task_name=path.relative_to(root).parts[0],
        section_name=_section_name_from_path(root, path),
        file_path=path.relative_to(root).as_posix(),
        size=path.stat().st_size,
    )


@router.delete(
    "/{task_name}/{section_name:path}",
    status_code=204,
    summary="Delete Proposal Draft",
)
async def delete_proposal_draft(task_name: str, section_name: str) -> None:
    """Delete a Markdown draft by task and section name."""
    _, path = _resolve_draft_path(task_name, section_name)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proposal draft not found.")
    path.unlink()
