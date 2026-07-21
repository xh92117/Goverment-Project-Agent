"""Knowledge-base API for government project declaration materials."""

import dataclasses
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.gateway.admin import require_admin_user
from deerflow.knowledge import (
    KnowledgeDocument,
    KnowledgeDocumentCreate,
    KnowledgeDocumentPatch,
    KnowledgeEvidence,
    KnowledgeEvidencePatch,
    KnowledgeFileReadRequest,
    KnowledgeFileReadResponse,
    KnowledgeFileSaveRequest,
    KnowledgeFileSaveResponse,
    KnowledgeIncrementalUpdateRequest,
    KnowledgeIncrementalUpdateResponse,
    KnowledgeIndexBuildRequest,
    KnowledgeIndexBuildResponse,
    KnowledgeIndexEntry,
    KnowledgeIndexEntryCreate,
    KnowledgeIndexEntryPatch,
    KnowledgeIndexListRequest,
    KnowledgeIndexListResponse,
    KnowledgeIndexSearchRequest,
    KnowledgeIndexSearchResponse,
    KnowledgeOrganizeResponse,
    KnowledgeRecallEvalRequest,
    KnowledgeRecallEvalResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    build_knowledge_index_from_folder,
    create_knowledge_document,
    create_knowledge_index_entry,
    delete_knowledge_document,
    delete_knowledge_evidence,
    delete_knowledge_index_entry,
    evaluate_knowledge_recall,
    get_knowledge_asset,
    get_knowledge_document,
    get_knowledge_evidence,
    get_knowledge_index_entry,
    ingest_knowledge_image,
    list_knowledge_documents,
    list_knowledge_index_entries,
    list_knowledge_index_entries_page,
    organize_incoming_files,
    organize_options_from_config,
    read_knowledge_file_combined,
    reextract_knowledge_evidence,
    resolve_asset_file,
    save_knowledge_file,
    search_knowledge_documents_combined,
    search_knowledge_evidence,
    search_knowledge_index_entries_combined,
    update_knowledge_document,
    update_knowledge_evidence,
    update_knowledge_index_entry,
)
from deerflow.knowledge import storage as knowledge_storage
from deerflow.runtime.user_context import get_effective_user_id
from deerflow.uploads.manager import (
    UnsafeUploadPathError,
    claim_unique_filename,
    normalize_filename,
    open_upload_file_no_symlink,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

KnowledgeScope = Literal["private", "public"]
KnowledgeReadScope = Literal["auto", "private", "public"]


def _scope_user_id(scope: KnowledgeScope) -> str | None:
    return None if scope == "public" else get_effective_user_id()


async def _authorize_public_write(scope: KnowledgeScope, request: Request) -> None:
    if scope == "public":
        await require_admin_user(request, resource="the public knowledge base")

UPLOAD_CHUNK_SIZE = 8192
KNOWLEDGE_MAX_FILES = 20
KNOWLEDGE_MAX_FILE_SIZE = 100 * 1024 * 1024
KNOWLEDGE_IMAGE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
KNOWLEDGE_SUPPORTED_UPLOAD_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".docx",
    ".pdf",
    ".xlsx",
    ".xls",
    ".csv",
    ".tsv",
    *KNOWLEDGE_IMAGE_UPLOAD_EXTENSIONS,
}


class KnowledgeUploadedFileInfo(BaseModel):
    """Uploaded knowledge-base file metadata."""

    filename: str
    size: int
    file_path: str
    incoming_path: str
    extension: str | None = None
    original_filename: str | None = None
    asset_id: str | None = None
    evidence_id: str | None = None
    deduplicated: bool | None = None


class KnowledgeUploadResponse(BaseModel):
    """Response model for uploading files into the knowledge-base incoming folder."""

    success: bool
    files: list[KnowledgeUploadedFileInfo]
    message: str
    skipped_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KnowledgeFileDeleteResponse(BaseModel):
    """Response after deleting a knowledge source file or generated chunk."""

    success: bool
    file_path: str
    delete_source: bool
    deleted_files: list[str] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    deleted_index_ids: list[str] = Field(default_factory=list)
    deleted_index_entries: int = 0
    version_backup_path: str | None = None
    message: str


class KnowledgeEvidenceDeleteResponse(BaseModel):
    success: bool
    evidence_id: str
    deleted_asset_ids: list[str] = Field(default_factory=list)


class KnowledgeEvidenceBatchReviewRequest(BaseModel):
    applicant_id: str = Field(default="default", min_length=1)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    verification_status: Literal["human_verified", "rejected"]
    review_notes: str = ""


class KnowledgeEvidenceBatchReviewResponse(BaseModel):
    updated: list[KnowledgeEvidence] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)


def _relative_to_knowledge_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _resolve_knowledge_folder(root: Path, folder_path: str) -> Path:
    raw = Path(folder_path)
    if raw.is_absolute():
        raise ValueError("folder_path must be relative to the knowledge-base root.")
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        raise ValueError("Access denied: path traversal detected.") from None
    return resolved


def _validate_deletable_knowledge_path(relative_path: str) -> None:
    parts = Path(relative_path).parts
    if not parts:
        raise ValueError("file_path must point to a file under the knowledge-base root.")
    if parts[0] == ".index_versions" or relative_path == "index.json":
        raise ValueError("Knowledge metadata files cannot be deleted through the file API.")
    if relative_path == "README.md":
        raise ValueError("Knowledge README cannot be deleted through the file API.")


def _source_file_for_index_entry(entry: KnowledgeIndexEntry) -> str:
    metadata_source = entry.metadata.get("source_file_path") if entry.metadata else None
    return entry.source_file_path or str(metadata_source or entry.file_path)


def _entry_matches_delete_target(
    entry: KnowledgeIndexEntry,
    relative_path: str,
    *,
    delete_source: bool,
) -> bool:
    if delete_source:
        return relative_path in {
            _source_file_for_index_entry(entry),
            entry.source_file_path or "",
            entry.file_path,
            entry.chunk_file_path or "",
        }
    return relative_path in {entry.file_path, entry.chunk_file_path or ""}


def _entry_files_to_delete(
    entry: KnowledgeIndexEntry,
    *,
    delete_source: bool,
) -> set[str]:
    files: set[str] = set()
    if entry.file_path:
        files.add(entry.file_path)
    if entry.chunk_file_path:
        files.add(entry.chunk_file_path)
    if delete_source and entry.source_file_path:
        files.add(entry.source_file_path)
    return files


def _related_mineru_cache_paths(root: Path, source_path: Path) -> set[Path]:
    cache_name = f"{source_path.name}.mineru.md"
    return {path for path in root.rglob(cache_name) if path.is_file()}


def _related_pdf_asset_paths(root: Path, source_path: Path) -> set[Path]:
    asset_dir_name = f"{source_path.name}.assets"
    return {path for path in root.rglob(asset_dir_name) if path.is_dir()}


def _remove_empty_parent_dirs(root: Path, start: Path) -> None:
    root = root.resolve()
    current = start.resolve()
    while current != root:
        try:
            current.relative_to(root)
        except ValueError:
            return
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _delete_file_if_present(root: Path, path: Path) -> tuple[bool, str]:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    relative_path = _relative_to_knowledge_root(root, resolved)
    if not resolved.exists():
        return False, relative_path
    if resolved.is_dir() and resolved.name.lower().endswith(".pdf.assets"):
        shutil.rmtree(resolved)
        _remove_empty_parent_dirs(root, resolved.parent)
        return True, relative_path
    if not resolved.is_file():
        raise ValueError(f"Knowledge path '{relative_path}' is not a file.")
    resolved.unlink()
    _remove_empty_parent_dirs(root, resolved.parent)
    return True, relative_path


def _delete_knowledge_file_and_indexes(
    *,
    root: Path,
    relative_path: str,
    delete_source: bool,
    user_id: str | None,
) -> KnowledgeFileDeleteResponse:
    storage = knowledge_storage.get_knowledge_storage()
    indexes = storage.list_indexes(user_id=user_id)
    matched_entries = [entry for entry in indexes if _entry_matches_delete_target(entry, relative_path, delete_source=delete_source)]
    matched_index_ids = {entry.index_id for entry in matched_entries}

    files_to_delete = {(root / relative_path).resolve()}
    for entry in matched_entries:
        for entry_file in _entry_files_to_delete(entry, delete_source=delete_source):
            files_to_delete.add((root / entry_file).resolve())

    if delete_source:
        source_path = (root / relative_path).resolve()
        files_to_delete.update(_related_mineru_cache_paths(root, source_path))
        files_to_delete.update(_related_pdf_asset_paths(root, source_path))
        for entry in matched_entries:
            source_file = _source_file_for_index_entry(entry)
            files_to_delete.update(_related_mineru_cache_paths(root, (root / source_file).resolve()))
            files_to_delete.update(_related_pdf_asset_paths(root, (root / source_file).resolve()))

    deleted_files: list[str] = []
    missing_files: list[str] = []
    for path in sorted(files_to_delete, key=lambda item: item.as_posix()):
        try:
            deleted, deleted_relative = _delete_file_if_present(root, path)
        except ValueError:
            continue
        if deleted:
            deleted_files.append(deleted_relative)
        else:
            missing_files.append(deleted_relative)

    version_backup_path = None
    if matched_index_ids:
        version_backup_path = knowledge_storage.backup_knowledge_index(user_id=user_id, reason="delete_file")
        storage.save_all_indexes(
            [entry for entry in indexes if entry.index_id not in matched_index_ids],
            user_id=user_id,
        )

    if not deleted_files and not matched_index_ids:
        raise FileNotFoundError(relative_path)

    return KnowledgeFileDeleteResponse(
        success=True,
        file_path=relative_path,
        delete_source=delete_source,
        deleted_files=deleted_files,
        missing_files=missing_files,
        deleted_index_ids=sorted(matched_index_ids),
        deleted_index_entries=len(matched_index_ids),
        version_backup_path=version_backup_path,
        message=f"Deleted {len(deleted_files)} file(s) and {len(matched_index_ids)} index entrie(s).",
    )


def _claim_available_filename(base_dir: Path, filename: str, seen: set[str]) -> str:
    candidate = claim_unique_filename(filename, seen)
    if not (base_dir / candidate).exists():
        return candidate

    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    counter = 1
    while True:
        next_name = claim_unique_filename(f"{stem}_{counter}{suffix}", seen)
        if not (base_dir / next_name).exists():
            return next_name
        counter += 1


async def _write_knowledge_upload_file(
    file: UploadFile,
    *,
    incoming_dir: Path,
    filename: str,
) -> tuple[Path, int]:
    file_size = 0
    file_path, fh = open_upload_file_no_symlink(incoming_dir, filename)
    try:
        while chunk := await file.read(UPLOAD_CHUNK_SIZE):
            file_size += len(chunk)
            if file_size > KNOWLEDGE_MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large: {filename}")
            fh.write(chunk)
    except Exception:
        fh.close()
        file_path.unlink(missing_ok=True)
        raise
    else:
        fh.close()
    return file_path, file_size


async def _read_knowledge_upload_bytes(file: UploadFile, *, filename: str) -> bytes:
    chunks: list[bytes] = []
    file_size = 0
    while chunk := await file.read(UPLOAD_CHUNK_SIZE):
        file_size += len(chunk)
        if file_size > KNOWLEDGE_MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File too large: {filename}")
        chunks.append(chunk)
    return b"".join(chunks)


def _word_upload_warning(files: list[KnowledgeUploadedFileInfo]) -> str | None:
    word_files = [item.filename for item in files if item.extension == ".docx"]
    if not word_files:
        return None
    return "检测到 Word 文件。为提高 MinerU 解析、公式图片保留和章节分块质量，建议将申报书另存为 PDF 后上传。"


def _run_incremental_update(
    request: KnowledgeIncrementalUpdateRequest,
    *,
    user_id: str | None,
) -> KnowledgeIncrementalUpdateResponse:
    organization = None
    if request.organize_incoming:
        report = organize_incoming_files(
            organize_options_from_config(request.model_dump(mode="json")),
            user_id=user_id,
        )
        organization = KnowledgeOrganizeResponse.model_validate(dataclasses.asdict(report))

    index_build = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(
            folder_path=request.folder_path,
            recursive=request.recursive,
            include_extensions=request.include_extensions,
            replace_existing=request.replace_existing,
            project_types=request.project_types,
            max_files=request.max_files,
            incremental=request.incremental,
        ),
        user_id=user_id,
    )
    return KnowledgeIncrementalUpdateResponse(organization=organization, index_build=index_build)


@router.get(
    "/documents",
    response_model=list[KnowledgeDocument],
    response_model_exclude_none=True,
    summary="List Knowledge Documents",
    description="List knowledge-base documents for the current user, optionally filtered by library and document type.",
)
async def list_documents(
    library: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    scope: KnowledgeScope = Query(default="private"),
) -> list[KnowledgeDocument]:
    """List knowledge-base documents."""
    return list_knowledge_documents(
        user_id=_scope_user_id(scope),
        library=library,
        doc_type=doc_type,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocument,
    response_model_exclude_none=True,
    summary="Create Knowledge Document",
    description="Create a knowledge-base document record with metadata and extracted content.",
)
async def create_document(
    body: KnowledgeDocumentCreate,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeDocument:
    """Create a knowledge-base document."""
    await _authorize_public_write(scope, request)
    return create_knowledge_document(body, user_id=_scope_user_id(scope))


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocument,
    response_model_exclude_none=True,
    summary="Get Knowledge Document",
    description="Get a single knowledge-base document by id.",
)
async def get_document(
    document_id: str,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeDocument:
    """Get a knowledge-base document."""
    try:
        return get_knowledge_document(document_id, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge document '{document_id}' not found.") from exc


@router.patch(
    "/documents/{document_id}",
    response_model=KnowledgeDocument,
    response_model_exclude_none=True,
    summary="Update Knowledge Document",
    description="Partially update a knowledge-base document.",
)
async def update_document(
    document_id: str,
    body: KnowledgeDocumentPatch,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeDocument:
    """Patch a knowledge-base document."""
    try:
        await _authorize_public_write(scope, request)
        return update_knowledge_document(document_id, body, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge document '{document_id}' not found.") from exc


@router.delete(
    "/documents/{document_id}",
    status_code=204,
    summary="Delete Knowledge Document",
    description="Delete a knowledge-base document by id.",
)
async def delete_document(
    document_id: str,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> None:
    """Delete a knowledge-base document."""
    try:
        await _authorize_public_write(scope, request)
        delete_knowledge_document(document_id, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge document '{document_id}' not found.") from exc


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    response_model_exclude_none=True,
    summary="Search Knowledge Base",
    description="Search knowledge-base documents with keyword matching, library filters, type filters, and metadata filters.",
)
async def search_knowledge(request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    """Search the current user's knowledge base."""
    return search_knowledge_documents_combined(request, user_id=get_effective_user_id())


@router.get(
    "/index",
    response_model=list[KnowledgeIndexEntry],
    response_model_exclude_none=True,
    summary="List Knowledge Index Entries",
    description="List LLM-Wiki index entries. Agents should search this index before reading source files.",
)
async def list_index_entries(
    category: str | None = Query(default=None),
    scope: KnowledgeScope = Query(default="private"),
) -> list[KnowledgeIndexEntry]:
    """List LLM-Wiki index entries."""
    return list_knowledge_index_entries(user_id=_scope_user_id(scope), category=category)


@router.post(
    "/index/page",
    response_model=KnowledgeIndexListResponse,
    response_model_exclude_none=True,
    summary="List Knowledge Index Entries Page",
    description="List LLM-Wiki index entries with pagination and optional local filtering.",
)
async def list_index_entries_page(
    body: KnowledgeIndexListRequest,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIndexListResponse:
    """List a paged slice of LLM-Wiki index entries."""
    return list_knowledge_index_entries_page(body, user_id=_scope_user_id(scope))


@router.post(
    "/index",
    response_model=KnowledgeIndexEntry,
    response_model_exclude_none=True,
    summary="Create Knowledge Index Entry",
    description="Create an LLM-Wiki index entry that points to a source file and optional sections.",
)
async def create_index_entry(
    body: KnowledgeIndexEntryCreate,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIndexEntry:
    """Create an LLM-Wiki index entry."""
    await _authorize_public_write(scope, request)
    return create_knowledge_index_entry(body, user_id=_scope_user_id(scope))


@router.get(
    "/index/{index_id}",
    response_model=KnowledgeIndexEntry,
    response_model_exclude_none=True,
    summary="Get Knowledge Index Entry",
    description="Get a single LLM-Wiki index entry.",
)
async def get_index_entry(
    index_id: str,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIndexEntry:
    """Get an LLM-Wiki index entry."""
    try:
        return get_knowledge_index_entry(index_id, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge index entry '{index_id}' not found.") from exc


@router.patch(
    "/index/{index_id}",
    response_model=KnowledgeIndexEntry,
    response_model_exclude_none=True,
    summary="Update Knowledge Index Entry",
    description="Partially update an LLM-Wiki index entry.",
)
async def update_index_entry(
    index_id: str,
    body: KnowledgeIndexEntryPatch,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIndexEntry:
    """Patch an LLM-Wiki index entry."""
    try:
        await _authorize_public_write(scope, request)
        return update_knowledge_index_entry(index_id, body, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge index entry '{index_id}' not found.") from exc


@router.delete(
    "/index/{index_id}",
    status_code=204,
    summary="Delete Knowledge Index Entry",
    description="Delete an LLM-Wiki index entry.",
)
async def delete_index_entry(
    index_id: str,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> None:
    """Delete an LLM-Wiki index entry."""
    try:
        await _authorize_public_write(scope, request)
        delete_knowledge_index_entry(index_id, user_id=_scope_user_id(scope))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge index entry '{index_id}' not found.") from exc


@router.post(
    "/index/search",
    response_model=KnowledgeIndexSearchResponse,
    response_model_exclude_none=True,
    summary="Search Knowledge Index",
    description="Search the LLM-Wiki index layer before reading source files.",
)
async def search_index(request: KnowledgeIndexSearchRequest) -> KnowledgeIndexSearchResponse:
    """Search LLM-Wiki index entries."""
    return search_knowledge_index_entries_combined(request, user_id=get_effective_user_id())


@router.post(
    "/index/evaluate",
    response_model=KnowledgeRecallEvalResponse,
    response_model_exclude_none=True,
    summary="Evaluate Knowledge Index Recall",
    description="Evaluate recall@k and MRR over a small expected-result set.",
)
async def evaluate_index_recall(
    body: KnowledgeRecallEvalRequest,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeRecallEvalResponse:
    """Evaluate knowledge index retrieval quality."""
    return evaluate_knowledge_recall(body, user_id=_scope_user_id(scope))


@router.post(
    "/index/build",
    response_model=KnowledgeIndexBuildResponse,
    response_model_exclude_none=True,
    summary="Build Knowledge Index",
    description="Scan a knowledge-base folder and build LLM-Wiki index entries from source files.",
)
async def build_index(
    body: KnowledgeIndexBuildRequest,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIndexBuildResponse:
    """Build LLM-Wiki index entries from a folder."""
    try:
        await _authorize_public_write(scope, request)
        return build_knowledge_index_from_folder(body, user_id=_scope_user_id(scope))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge folder '{body.folder_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/index/incremental-update",
    response_model=KnowledgeIncrementalUpdateResponse,
    response_model_exclude_none=True,
    summary="Incrementally Update Knowledge Index",
    description="Organize files from the incoming folder and then rebuild the LLM-Wiki index.",
)
async def incremental_update(
    body: KnowledgeIncrementalUpdateRequest,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIncrementalUpdateResponse:
    """One-click organization of incoming files and LLM-Wiki index update."""
    await _authorize_public_write(scope, request)
    user_id = _scope_user_id(scope)
    try:
        return _run_incremental_update(body, user_id=user_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge folder '{body.folder_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/index/process-incoming",
    response_model=KnowledgeIncrementalUpdateResponse,
    response_model_exclude_none=True,
    summary="Process Incoming Files And Build Index",
    description="Organize files from incoming and rebuild the LLM-Wiki index as one user action.",
)
async def process_incoming_and_build_index(
    body: KnowledgeIncrementalUpdateRequest,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeIncrementalUpdateResponse:
    """Bind incoming-file organization and index building into a single action."""
    await _authorize_public_write(scope, request)
    user_id = _scope_user_id(scope)
    try:
        body.organize_incoming = True
        body.replace_existing = True
        return _run_incremental_update(body, user_id=user_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge folder '{body.folder_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/files/upload",
    response_model=KnowledgeUploadResponse,
    response_model_exclude_none=True,
    summary="Upload Knowledge Files",
    description="Upload files into the knowledge-base incoming folder before organization and indexing.",
)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    incoming_path: str = Query(default="_incoming"),
    applicant_id: str = Query(default="default"),
    evidence_type: str = Query(default="image_evidence"),
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeUploadResponse:
    """Upload source files into the knowledge-base incoming folder."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > KNOWLEDGE_MAX_FILES:
        raise HTTPException(status_code=413, detail=f"Too many files: maximum is {KNOWLEDGE_MAX_FILES}")

    await _authorize_public_write(scope, request)
    user_id = _scope_user_id(scope)
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    try:
        incoming_dir = _resolve_knowledge_folder(root, incoming_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    incoming_dir.mkdir(parents=True, exist_ok=True)

    uploaded_files: list[KnowledgeUploadedFileInfo] = []
    skipped_files: list[str] = []
    seen_filenames: set[str] = set()

    for file in files:
        if not file.filename:
            skipped_files.append("(empty filename)")
            continue
        try:
            original_filename = normalize_filename(file.filename)
            extension = Path(original_filename).suffix.lower()
            if extension not in KNOWLEDGE_SUPPORTED_UPLOAD_EXTENSIONS:
                skipped_files.append(original_filename)
                continue
            if extension in KNOWLEDGE_IMAGE_UPLOAD_EXTENSIONS:
                data = await _read_knowledge_upload_bytes(file, filename=original_filename)
                asset, evidence, deduplicated = ingest_knowledge_image(
                    data,
                    filename=original_filename,
                    applicant_id=applicant_id,
                    evidence_type=evidence_type,
                    user_id=user_id,
                )
                uploaded_files.append(
                    KnowledgeUploadedFileInfo(
                        filename=original_filename,
                        size=asset.byte_size,
                        file_path=asset.storage_path,
                        incoming_path=".assets",
                        extension=extension,
                        asset_id=asset.asset_id,
                        evidence_id=evidence.evidence_id,
                        deduplicated=deduplicated,
                    )
                )
                continue
            safe_filename = _claim_available_filename(incoming_dir, original_filename, seen_filenames)
            file_path, file_size = await _write_knowledge_upload_file(
                file,
                incoming_dir=incoming_dir,
                filename=safe_filename,
            )
        except UnsafeUploadPathError:
            skipped_files.append(file.filename)
            continue
        except ValueError:
            skipped_files.append(file.filename)
            continue
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {exc}") from exc

        uploaded_files.append(
            KnowledgeUploadedFileInfo(
                filename=safe_filename,
                size=file_size,
                file_path=_relative_to_knowledge_root(root, file_path),
                incoming_path=_relative_to_knowledge_root(root, incoming_dir),
                extension=file_path.suffix.lower(),
                original_filename=original_filename if original_filename != safe_filename else None,
            )
        )

    message = f"Uploaded {len(uploaded_files)} knowledge file(s) to {incoming_path}"
    if skipped_files:
        message += f"; skipped {len(skipped_files)} unsupported or unsafe file(s)"
    warnings = []
    word_warning = _word_upload_warning(uploaded_files)
    if word_warning:
        warnings.append(word_warning)

    return KnowledgeUploadResponse(
        success=bool(uploaded_files) and not skipped_files,
        files=uploaded_files,
        message=message,
        skipped_files=skipped_files,
        warnings=warnings,
    )


@router.get(
    "/assets/{asset_id}/content",
    response_class=FileResponse,
    summary="Read Knowledge Image Asset",
    description="Read an original knowledge image after validating its applicant owner.",
)
async def read_asset_content(
    asset_id: str,
    applicant_id: str = Query(..., min_length=1),
    thumbnail: bool = Query(default=False),
) -> FileResponse:
    user_id = get_effective_user_id()
    try:
        asset = get_knowledge_asset(asset_id, applicant_id=applicant_id, user_id=user_id)
        resolved = resolve_asset_file(asset, thumbnail=thumbnail, user_id=user_id)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge asset '{asset_id}' not found.") from exc
    media_type = "image/webp" if thumbnail else asset.mime_type
    filename = f"thumbnail-{asset.original_filename}.webp" if thumbnail else asset.original_filename
    return FileResponse(path=resolved, filename=filename, media_type=media_type)


@router.get(
    "/evidence",
    response_model=list[KnowledgeEvidence],
    response_model_exclude_none=True,
    summary="Search Knowledge Evidence",
)
async def search_evidence(
    applicant_id: str = Query(..., min_length=1),
    query: str = Query(default=""),
    evidence_type: list[str] | None = Query(default=None),
    verification_status: list[str] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[KnowledgeEvidence]:
    return search_knowledge_evidence(
        query=query,
        applicant_id=applicant_id,
        evidence_types=evidence_type,
        verification_statuses=verification_status,
        limit=limit,
        user_id=get_effective_user_id(),
    )


@router.post(
    "/evidence/batch-review",
    response_model=KnowledgeEvidenceBatchReviewResponse,
    response_model_exclude_none=True,
    summary="Batch Review Knowledge Evidence",
)
async def batch_review_evidence(
    request: KnowledgeEvidenceBatchReviewRequest,
) -> KnowledgeEvidenceBatchReviewResponse:
    user_id = get_effective_user_id()
    updated: list[KnowledgeEvidence] = []
    skipped: dict[str, str] = {}
    for evidence_id in dict.fromkeys(request.evidence_ids):
        try:
            updated.append(
                update_knowledge_evidence(
                    evidence_id,
                    KnowledgeEvidencePatch(
                        verification_status=request.verification_status,
                        review_notes=request.review_notes,
                    ),
                    applicant_id=request.applicant_id,
                    user_id=user_id,
                )
            )
        except KeyError:
            skipped[evidence_id] = "Evidence was not found for this applicant."
        except ValueError as exc:
            skipped[evidence_id] = str(exc)
    return KnowledgeEvidenceBatchReviewResponse(updated=updated, skipped=skipped)


@router.get(
    "/evidence/{evidence_id}",
    response_model=KnowledgeEvidence,
    response_model_exclude_none=True,
    summary="Get Knowledge Evidence",
)
async def get_evidence(evidence_id: str, applicant_id: str = Query(..., min_length=1)) -> KnowledgeEvidence:
    try:
        return get_knowledge_evidence(evidence_id, applicant_id=applicant_id, user_id=get_effective_user_id())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge evidence '{evidence_id}' not found.") from exc


@router.post(
    "/evidence/{evidence_id}/extract",
    response_model=KnowledgeEvidence,
    response_model_exclude_none=True,
    summary="Re-extract Knowledge Evidence",
)
async def extract_evidence(
    evidence_id: str,
    applicant_id: str = Query(..., min_length=1),
) -> KnowledgeEvidence:
    try:
        return reextract_knowledge_evidence(
            evidence_id,
            applicant_id=applicant_id,
            user_id=get_effective_user_id(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge evidence '{evidence_id}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch(
    "/evidence/{evidence_id}",
    response_model=KnowledgeEvidence,
    response_model_exclude_none=True,
    summary="Review Knowledge Evidence",
)
async def patch_evidence(
    evidence_id: str,
    request: KnowledgeEvidencePatch,
    applicant_id: str = Query(..., min_length=1),
) -> KnowledgeEvidence:
    try:
        return update_knowledge_evidence(
            evidence_id,
            request,
            applicant_id=applicant_id,
            user_id=get_effective_user_id(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge evidence '{evidence_id}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/evidence/{evidence_id}",
    response_model=KnowledgeEvidenceDeleteResponse,
    summary="Delete Knowledge Evidence",
)
async def delete_evidence(
    evidence_id: str,
    applicant_id: str = Query(..., min_length=1),
) -> KnowledgeEvidenceDeleteResponse:
    try:
        asset_ids = delete_knowledge_evidence(
            evidence_id,
            applicant_id=applicant_id,
            user_id=get_effective_user_id(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge evidence '{evidence_id}' not found.") from exc
    return KnowledgeEvidenceDeleteResponse(success=True, evidence_id=evidence_id, deleted_asset_ids=asset_ids)


@router.get(
    "/files/download",
    response_class=FileResponse,
    summary="Download Knowledge File",
    description="Download a source file by path relative to the knowledge-base root.",
)
async def download_file(
    file_path: str = Query(..., min_length=1),
    scope: KnowledgeReadScope = Query(default="auto"),
) -> FileResponse:
    """Download a source file from the knowledge base."""
    user_id = get_effective_user_id()
    scope_ids = [user_id, None] if scope == "auto" else [_scope_user_id(scope)]
    for scope_user_id in scope_ids:
        root = knowledge_storage._knowledge_root_path(user_id=scope_user_id)
        try:
            resolved = _resolve_knowledge_folder(root, file_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if resolved.exists() and resolved.is_file():
            return FileResponse(path=resolved, filename=resolved.name, media_type="application/octet-stream")
    raise HTTPException(status_code=404, detail=f"Knowledge file '{file_path}' not found.")


@router.delete(
    "/files",
    response_model=KnowledgeFileDeleteResponse,
    response_model_exclude_none=True,
    summary="Delete Knowledge File",
    description=("Delete a source file or generated chunk and remove associated LLM-Wiki index entries. With delete_source=true, all chunks and MinerU caches for the source file are removed too."),
)
async def delete_file(
    request: Request,
    file_path: str = Query(..., min_length=1),
    delete_source: bool = Query(default=True),
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeFileDeleteResponse:
    """Delete a knowledge file and synchronize generated chunks and index records."""
    await _authorize_public_write(scope, request)
    user_id = _scope_user_id(scope)
    root = knowledge_storage._knowledge_root_path(user_id=user_id)
    try:
        resolved = _resolve_knowledge_folder(root, file_path)
        relative_path = _relative_to_knowledge_root(root, resolved)
        _validate_deletable_knowledge_path(relative_path)
        return _delete_knowledge_file_and_indexes(
            root=root,
            relative_path=relative_path,
            delete_source=delete_source,
            user_id=user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge file '{file_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete knowledge file '{file_path}': {exc}") from exc


@router.post(
    "/files/read",
    response_model=KnowledgeFileReadResponse,
    response_model_exclude_none=True,
    summary="Read Knowledge File",
    description="Read a knowledge-base file or markdown section by path relative to the knowledge-base root.",
)
async def read_file(
    body: KnowledgeFileReadRequest,
    scope: KnowledgeReadScope = Query(default="auto"),
) -> KnowledgeFileReadResponse:
    """Read a source file referenced by the LLM-Wiki index."""
    try:
        return read_knowledge_file_combined(body, user_id=get_effective_user_id(), scope=scope)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge file '{body.file_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/files/save",
    response_model=KnowledgeFileSaveResponse,
    response_model_exclude_none=True,
    summary="Save Knowledge File",
    description="Save an editable markdown or plain-text knowledge-base file by path relative to the knowledge-base root.",
)
async def save_file(
    body: KnowledgeFileSaveRequest,
    request: Request,
    scope: KnowledgeScope = Query(default="private"),
) -> KnowledgeFileSaveResponse:
    """Save a markdown/text knowledge file referenced by the LLM-Wiki index."""
    try:
        await _authorize_public_write(scope, request)
        return save_knowledge_file(body, user_id=_scope_user_id(scope))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Knowledge file '{body.file_path}' not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save knowledge file '{body.file_path}': {exc}") from exc
