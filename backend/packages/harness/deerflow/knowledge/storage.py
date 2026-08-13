"""File-backed storage for the lightweight project declaration knowledge base."""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from deerflow.config.paths import get_paths
from deerflow.government_project_workspace import government_project_knowledge_root
from deerflow.knowledge.extractors import extract_text
from deerflow.knowledge.schemas import (
    KnowledgeDocument,
    KnowledgeDocumentCreate,
    KnowledgeDocumentPatch,
    KnowledgeFileReadRequest,
    KnowledgeFileReadResponse,
    KnowledgeFileSaveRequest,
    KnowledgeFileSaveResponse,
    KnowledgeIndexEntry,
    KnowledgeIndexEntryCreate,
    KnowledgeIndexEntryPatch,
    KnowledgeIndexListRequest,
    KnowledgeIndexListResponse,
    KnowledgeIndexSearchRequest,
    KnowledgeIndexSearchResponse,
    KnowledgeIndexSearchResult,
    KnowledgeRecallEvalCase,
    KnowledgeRecallEvalCaseResult,
    KnowledgeRecallEvalRequest,
    KnowledgeRecallEvalResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
)
from deerflow.knowledge.semantic_search import expand_knowledge_index_search_request
from deerflow.knowledge.sqlite_index import (
    search_sqlite_knowledge_index_candidates,
    sync_sqlite_knowledge_index,
)
from deerflow.knowledge.vector_search import semantic_similarity
from deerflow.utils.time import now_iso

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = "1.0"
_MAX_INDEX_SEARCH_SCORE = 100.0
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_QUERY_STOPWORDS = (
    "请",
    "帮我",
    "查看",
    "查询",
    "查找",
    "了解",
    "一下",
    "相关",
    "内容",
    "资料",
    "材料",
    "情况",
    "的",
)
_KNOWLEDGE_QUERY_PHRASES = (
    "国内外研究现状",
    "国内研究现状",
    "国外研究现状",
    "研究现状",
    "发展动态",
    "发展趋势",
    "研究内容",
    "主要研究内容",
    "研究方案",
    "技术方案",
    "技术路线",
    "实验手段",
    "关键技术",
    "研究基础",
    "创新点",
    "申报条件",
    "路基填方施工质量",
    "填方施工质量",
    "现场检测技术",
    "现场检测",
    "检测技术",
    "质量评估",
    "填方材料",
    "施工质量",
    "回弹模量",
    "变形模量",
    "压实度",
    "落球",
    "路基",
    "填方",
)


def _empty_store() -> dict[str, Any]:
    return {
        "version": _SCHEMA_VERSION,
        "documents": [],
        "indexes": [],
    }


def _knowledge_file_path(*, user_id: str | None = None) -> Path:
    return _knowledge_root_path(user_id=user_id) / "index.json"


def _index_versions_dir(*, user_id: str | None = None) -> Path:
    return _knowledge_root_path(user_id=user_id) / ".index_versions"


def _knowledge_root_path(*, user_id: str | None = None) -> Path:
    if user_id:
        return (get_paths().user_dir(user_id) / "knowledge_base").resolve()
    return government_project_knowledge_root().resolve()


def _metadata_value_matches(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        return expected in actual
    return actual == expected


def _flatten_metadata(metadata: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in metadata.items():
        parts.append(str(key))
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.append(_flatten_metadata(value))
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts)


def _join_values(values: Iterable[Any]) -> str:
    return " ".join(str(value) for value in values if value is not None)


def _query_terms(query: str) -> list[str]:
    """Extract searchable terms from natural Chinese/English user queries."""

    lower = query.lower()
    terms: list[str] = []

    for term in re.split(r"\s+", lower):
        cleaned = term.strip()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)

    for phrase in _KNOWLEDGE_QUERY_PHRASES:
        if phrase.lower() in lower and phrase.lower() not in terms:
            terms.append(phrase.lower())

    compact = lower
    for stopword in _QUERY_STOPWORDS:
        compact = compact.replace(stopword, "")
    for chunk in _CJK_RE.findall(compact):
        if len(chunk) < 3:
            continue
        for length in range(min(8, len(chunk)), 2, -1):
            for start in range(0, len(chunk) - length + 1):
                gram = chunk[start : start + length]
                if gram not in terms:
                    terms.append(gram)
        if chunk not in terms:
            terms.append(chunk)

    return terms


def _make_snippet(text: str, query: str, *, max_length: int = 240) -> str:
    if not text:
        return ""
    if not query:
        return text[:max_length]
    lower = text.lower()
    pos = lower.find(query.lower())
    if pos < 0:
        return text[:max_length]
    start = max(0, pos - 80)
    end = min(len(text), pos + len(query) + 160)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _score_document(document: KnowledgeDocument, query: str) -> tuple[float, list[str]]:
    if not query:
        return 1.0, []

    query_terms = _query_terms(query)
    if not query_terms:
        return 1.0, []

    fields = {
        "title": document.title,
        "doc_type": document.doc_type,
        "library": document.library,
        "content": document.content,
        "metadata": _flatten_metadata(document.metadata),
        "source": document.source or "",
    }
    score = 0.0
    matched: list[str] = []
    weights = {
        "title": 4.0,
        "doc_type": 2.0,
        "library": 1.5,
        "content": 1.0,
        "metadata": 2.0,
        "source": 1.0,
    }
    for field, value in fields.items():
        haystack = str(value).lower()
        hits = sum(1 for term in query_terms if term in haystack)
        if hits:
            matched.append(field)
            score += hits * weights[field]
    return score, matched


def _score_index_entry(entry: KnowledgeIndexEntry, query: str) -> tuple[float, list[str]]:
    if not query:
        return 1.0, []

    query_terms = _query_terms(query)
    if not query_terms:
        return 1.0, []

    fields = {
        "title": entry.title,
        "category": entry.category,
        "domain": entry.domain or "",
        "authority": entry.authority or "",
        "document_type": entry.document_type or "",
        "year": str(entry.year or ""),
        "keywords": _join_values(entry.keywords),
        "technical_terms": _join_values(entry.technical_terms),
        "methods": _join_values(entry.methods),
        "research_objects": _join_values(entry.research_objects),
        "proposal_sections": _join_values(entry.proposal_sections),
        "evidence_type": entry.evidence_type or "",
        "evidence_id": entry.evidence_id or "",
        "applicant_id": entry.applicant_id or "",
        "verification_status": entry.verification_status or "",
        "source_anchor": entry.source_anchor or "",
        "source_file_path": entry.source_file_path or "",
        "summary": entry.summary,
        "file_path": entry.file_path,
        "project_types": _join_values(entry.project_types),
    }
    weights = {
        "title": 5.0,
        "category": 4.0,
        "domain": 3.0,
        "authority": 8.0,
        "document_type": 7.0,
        "year": 9.0,
        "keywords": 4.0,
        "technical_terms": 5.0,
        "methods": 4.0,
        "research_objects": 4.0,
        "proposal_sections": 6.0,
        "evidence_type": 2.0,
        "evidence_id": 1.0,
        "applicant_id": 3.0,
        "verification_status": 1.0,
        "source_anchor": 5.0,
        "source_file_path": 1.0,
        "summary": 2.0,
        "file_path": 2.0,
        "project_types": 2.0,
    }
    score = 0.0
    matched: list[str] = []
    for field, value in fields.items():
        haystack = str(value).lower()
        hits = sum(1 for term in query_terms if term in haystack)
        if hits:
            matched.append(field)
            score += hits * weights[field]
    normalized_query = " ".join(query.casefold().split())
    if normalized_query:
        for field, bonus in (("title", 12.0), ("source_anchor", 10.0), ("keywords", 8.0)):
            normalized_value = " ".join(str(fields[field]).casefold().split())
            if normalized_query == normalized_value:
                score += bonus
                if field not in matched:
                    matched.append(field)
    return score, matched


def _index_entry_semantic_text(entry: KnowledgeIndexEntry) -> str:
    recommended = " ".join(" ".join([section.heading, section.anchor or "", section.summary, _join_values(section.use_for)]) for section in entry.recommended_sections)
    return " ".join(
        [
            entry.title,
            entry.category,
            entry.domain or "",
            entry.authority or "",
            entry.document_type or "",
            str(entry.year or ""),
            _join_values(entry.keywords),
            _join_values(entry.technical_terms),
            _join_values(entry.methods),
            _join_values(entry.research_objects),
            _join_values(entry.proposal_sections),
            _join_values(entry.applicable_chapters),
            entry.evidence_type or "",
            entry.evidence_id or "",
            entry.applicant_id or "",
            entry.verification_status or "",
            entry.valid_from or "",
            entry.valid_to or "",
            entry.source_anchor or "",
            entry.source_file_path or "",
            entry.summary,
            entry.file_path,
            _join_values(entry.project_types),
            _flatten_metadata(entry.metadata),
            recommended,
        ]
    )


def _score_index_entry_semantic(entry: KnowledgeIndexEntry, query: str) -> float:
    return semantic_similarity(query, _index_entry_semantic_text(entry))


def _bounded_index_search_score(score: float) -> float:
    return max(0.0, min(_MAX_INDEX_SEARCH_SCORE, score))


def _list_intersects(actual: Iterable[str], expected: Iterable[str]) -> bool:
    actual_set = {item.lower() for item in actual}
    return any(item.lower() in actual_set for item in expected)


def _optional_text_matches(actual: str | None, expected: Iterable[str]) -> bool:
    if not actual:
        return False
    normalized = actual.casefold().strip()
    return any(normalized == item.casefold().strip() for item in expected)


def _entry_valid_on(entry: KnowledgeIndexEntry, valid_on: str | None) -> bool:
    if not valid_on:
        return True
    target = valid_on.strip()[:10]
    if entry.valid_from and entry.valid_from.strip()[:10] > target:
        return False
    return not (entry.valid_to and entry.valid_to.strip()[:10] < target)


def _lexical_queries(request: KnowledgeIndexSearchRequest, expanded_query: str) -> list[tuple[str, float]]:
    queries: list[tuple[str, float]] = []
    seen: set[str] = set()
    for query, weight in (
        (request.query, 1.0),
        *((query, 0.65) for query in request.query_variants),
        (expanded_query, 0.25),
    ):
        normalized = " ".join(query.split())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        queries.append((normalized, weight))
    return queries


def _resolve_knowledge_file(file_path: str, *, user_id: str | None = None) -> Path:
    raw = Path(file_path)
    if raw.is_absolute():
        raise ValueError("file_path must be relative to the knowledge-base root.")
    root = _knowledge_root_path(user_id=user_id)
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError("Access denied: path traversal detected.") from None
    return resolved


_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_EDITABLE_KNOWLEDGE_EXTENSIONS = {".md", ".markdown", ".txt"}


def _normalize_anchor(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("#"):
        stripped = stripped.lstrip("#").strip()
    return stripped.casefold()


def _extract_markdown_section(content: str, anchor: str) -> str:
    target = _normalize_anchor(anchor)
    lines = content.splitlines()
    start: int | None = None
    start_level = 0
    fuzzy_candidates: list[tuple[int, int, int]] = []

    for index, line in enumerate(lines):
        match = _MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(2).strip()
        normalized_heading = _normalize_anchor(heading)
        if normalized_heading == target:
            start = index
            start_level = len(match.group(1))
            break
        if target in normalized_heading or normalized_heading in target:
            fuzzy_candidates.append((len(heading), index, len(match.group(1))))

    if start is None and fuzzy_candidates:
        _, start, start_level = min(fuzzy_candidates, key=lambda item: item[0])

    if start is None:
        return ""

    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = _MARKDOWN_HEADING_RE.match(lines[index])
        if match and len(match.group(1)) <= start_level:
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _find_markdown_section_bounds(content: str, anchor: str) -> tuple[int, int] | None:
    target = _normalize_anchor(anchor)
    lines = content.splitlines()
    start: int | None = None
    start_level = 0
    fuzzy_candidates: list[tuple[int, int, int]] = []

    for index, line in enumerate(lines):
        match = _MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(2).strip()
        normalized_heading = _normalize_anchor(heading)
        if normalized_heading == target:
            start = index
            start_level = len(match.group(1))
            break
        if target in normalized_heading or normalized_heading in target:
            fuzzy_candidates.append((len(heading), index, len(match.group(1))))

    if start is None and fuzzy_candidates:
        _, start, start_level = min(fuzzy_candidates, key=lambda item: item[0])

    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = _MARKDOWN_HEADING_RE.match(lines[index])
        if match and len(match.group(1)) <= start_level:
            end = index
            break
    return start, end


def _replace_markdown_section(content: str, anchor: str, replacement: str) -> str:
    bounds = _find_markdown_section_bounds(content, anchor)
    if bounds is None:
        raise ValueError(f"Markdown anchor '{anchor}' was not found.")

    start, end = bounds
    lines = content.splitlines()
    replacement_lines = replacement.strip().splitlines()
    next_lines = [*lines[:start], *replacement_lines, *lines[end:]]
    return "\n".join(next_lines).rstrip() + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


class KnowledgeBaseStorage:
    """Abstract-ish base class for knowledge-base storage providers."""

    def list(self, *, user_id: str | None = None) -> list[KnowledgeDocument]:
        raise NotImplementedError

    def save_all(self, documents: Iterable[KnowledgeDocument], *, user_id: str | None = None) -> None:
        raise NotImplementedError

    def list_indexes(self, *, user_id: str | None = None) -> list[KnowledgeIndexEntry]:
        raise NotImplementedError

    def save_all_indexes(self, indexes: Iterable[KnowledgeIndexEntry], *, user_id: str | None = None) -> None:
        raise NotImplementedError


class FileKnowledgeBaseStorage(KnowledgeBaseStorage):
    """JSON-file-backed knowledge-base storage.

    This is intentionally small and dependency-free for the MVP. It gives the
    API and agent tools a stable contract before a database/vector index is
    introduced.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _load_raw(self, *, user_id: str | None = None) -> dict[str, Any]:
        path = _knowledge_file_path(user_id=user_id)
        if not path.exists():
            return _empty_store()
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return _empty_store()
            data.setdefault("version", _SCHEMA_VERSION)
            data.setdefault("documents", [])
            data.setdefault("indexes", [])
            return data
        except (OSError, json.JSONDecodeError):
            logger.warning("Failed to load knowledge base file: %s", path, exc_info=True)
            return _empty_store()

    def list(self, *, user_id: str | None = None) -> list[KnowledgeDocument]:
        with self._lock:
            raw = self._load_raw(user_id=user_id)
            return [KnowledgeDocument(**item) for item in raw.get("documents", [])]

    def save_all(self, documents: Iterable[KnowledgeDocument], *, user_id: str | None = None) -> None:
        raw = self._load_raw(user_id=user_id)
        raw["documents"] = [document.model_dump(mode="json") for document in documents]
        self._save_raw(raw, user_id=user_id)

    def list_indexes(self, *, user_id: str | None = None) -> list[KnowledgeIndexEntry]:
        with self._lock:
            raw = self._load_raw(user_id=user_id)
            return [KnowledgeIndexEntry(**item) for item in raw.get("indexes", [])]

    def save_all_indexes(self, indexes: Iterable[KnowledgeIndexEntry], *, user_id: str | None = None) -> None:
        entry_list = list(indexes)
        raw = self._load_raw(user_id=user_id)
        dumped_indexes = []
        for entry in entry_list:
            payload = entry.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            payload["entry_type"] = entry.entry_type
            dumped_indexes.append(payload)
        raw["indexes"] = dumped_indexes
        self._save_raw(raw, user_id=user_id)
        try:
            sync_sqlite_knowledge_index(entry_list, root=_knowledge_root_path(user_id=user_id))
        except Exception:
            logger.warning("Failed to sync SQLite knowledge index.", exc_info=True)

    def _save_raw(self, raw: dict[str, Any], *, user_id: str | None = None) -> None:
        path = _knowledge_file_path(user_id=user_id)
        payload = {
            "version": raw.get("version", _SCHEMA_VERSION),
            "documents": raw.get("documents", []),
            "indexes": raw.get("indexes", []),
        }

        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            temp_path.replace(path)


_storage_instance: KnowledgeBaseStorage | None = None
_storage_lock = threading.Lock()


def get_knowledge_storage() -> KnowledgeBaseStorage:
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance
    with _storage_lock:
        if _storage_instance is None:
            _storage_instance = FileKnowledgeBaseStorage()
    return _storage_instance


def backup_knowledge_index(
    *,
    user_id: str | None = None,
    reason: str = "build_index",
) -> str | None:
    """Copy the current index.json into a timestamped version file.

    The returned path is relative to the knowledge-base root so API responses
    do not expose host-specific absolute paths unless callers already know the
    configured root.
    """

    source = _knowledge_file_path(user_id=user_id)
    if not source.exists():
        return None

    root = _knowledge_root_path(user_id=user_id)
    versions_dir = _index_versions_dir(user_id=user_id)
    versions_dir.mkdir(parents=True, exist_ok=True)
    version_id = now_iso().replace(":", "").replace("-", "").replace(".", "_")
    backup_path = versions_dir / f"index_{version_id}.json"
    shutil.copy2(source, backup_path)

    try:
        with source.open(encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _empty_store()

    manifest_path = versions_dir / "manifest.json"
    try:
        with manifest_path.open(encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception:
        manifest = {"versions": []}
    versions = manifest.setdefault("versions", [])
    versions.append(
        {
            "version_id": version_id,
            "created_at": now_iso(),
            "reason": reason,
            "backup_path": backup_path.relative_to(root).as_posix(),
            "entries_count": len(data.get("indexes", [])),
            "documents_count": len(data.get("documents", [])),
        }
    )
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return backup_path.relative_to(root).as_posix()


def list_knowledge_documents(
    *,
    user_id: str | None = None,
    library: str | None = None,
    doc_type: str | None = None,
) -> list[KnowledgeDocument]:
    documents = get_knowledge_storage().list(user_id=user_id)
    if library:
        documents = [document for document in documents if document.library == library]
    if doc_type:
        documents = [document for document in documents if document.doc_type == doc_type]
    return documents


def get_knowledge_document(document_id: str, *, user_id: str | None = None) -> KnowledgeDocument:
    for document in get_knowledge_storage().list(user_id=user_id):
        if document.document_id == document_id:
            return document
    raise KeyError(document_id)


def create_knowledge_document(request: KnowledgeDocumentCreate, *, user_id: str | None = None) -> KnowledgeDocument:
    storage = get_knowledge_storage()
    documents = storage.list(user_id=user_id)
    timestamp = now_iso()
    document = KnowledgeDocument(
        document_id=f"kb_{uuid.uuid4().hex}",
        title=request.title.strip(),
        library=request.library,
        doc_type=request.doc_type.strip(),
        content=request.content,
        metadata=request.metadata,
        source=request.source,
        source_uri=request.source_uri,
        confidentiality_level=request.confidentiality_level,
        created_at=timestamp,
        updated_at=timestamp,
    )
    documents.append(document)
    storage.save_all(documents, user_id=user_id)
    return document


def update_knowledge_document(
    document_id: str,
    request: KnowledgeDocumentPatch,
    *,
    user_id: str | None = None,
) -> KnowledgeDocument:
    storage = get_knowledge_storage()
    documents = storage.list(user_id=user_id)
    updated: KnowledgeDocument | None = None
    patch = request.model_dump(exclude_unset=True)

    for index, document in enumerate(documents):
        if document.document_id != document_id:
            continue
        data = document.model_dump()
        data.update(patch)
        data["updated_at"] = now_iso()
        updated = KnowledgeDocument(**data)
        documents[index] = updated
        break

    if updated is None:
        raise KeyError(document_id)

    storage.save_all(documents, user_id=user_id)
    return updated


def delete_knowledge_document(document_id: str, *, user_id: str | None = None) -> None:
    storage = get_knowledge_storage()
    documents = storage.list(user_id=user_id)
    kept = [document for document in documents if document.document_id != document_id]
    if len(kept) == len(documents):
        raise KeyError(document_id)
    storage.save_all(kept, user_id=user_id)


def search_knowledge_documents(
    request: KnowledgeSearchRequest,
    *,
    user_id: str | None = None,
) -> KnowledgeSearchResponse:
    documents = get_knowledge_storage().list(user_id=user_id)
    results: list[KnowledgeSearchResult] = []

    for document in documents:
        if request.libraries and document.library not in request.libraries:
            continue
        if request.doc_types and document.doc_type not in request.doc_types:
            continue
        if not request.include_restricted and document.confidentiality_level == "restricted":
            continue
        if any(not _metadata_value_matches(document.metadata.get(key), value) for key, value in request.metadata_filters.items()):
            continue

        score, matched_fields = _score_document(document, request.query)
        if request.query and score <= 0:
            continue

        results.append(
            KnowledgeSearchResult(
                document=document,
                score=score,
                matched_fields=matched_fields,
                snippet=_make_snippet(document.content, request.query),
            )
        )

    results.sort(key=lambda result: (result.score, result.document.updated_at), reverse=True)
    limited = results[: request.limit]
    return KnowledgeSearchResponse(results=limited, count=len(limited))


def search_knowledge_documents_combined(
    request: KnowledgeSearchRequest,
    *,
    user_id: str,
) -> KnowledgeSearchResponse:
    """Return public documents plus only the caller's private documents."""
    private_response = search_knowledge_documents(request, user_id=user_id)
    if _knowledge_root_path(user_id=user_id) == _knowledge_root_path(user_id=None):
        return private_response
    public_response = search_knowledge_documents(request, user_id=None)
    combined = [result.model_copy(update={"scope": "private"}) for result in private_response.results]
    combined.extend(result.model_copy(update={"scope": "public"}) for result in public_response.results)
    combined.sort(
        key=lambda result: (
            result.score,
            result.scope == "private",
            result.document.updated_at,
        ),
        reverse=True,
    )
    limited = combined[: request.limit]
    return KnowledgeSearchResponse(results=limited, count=len(limited))


def list_knowledge_index_entries(
    *,
    user_id: str | None = None,
    category: str | None = None,
) -> list[KnowledgeIndexEntry]:
    entries = get_knowledge_storage().list_indexes(user_id=user_id)
    if category:
        entries = [entry for entry in entries if entry.category == category]
    return entries


def list_knowledge_index_entries_page(
    request: KnowledgeIndexListRequest,
    *,
    user_id: str | None = None,
) -> KnowledgeIndexListResponse:
    entries = list_knowledge_index_entries(user_id=user_id, category=request.category)
    query = request.query.strip()
    if query:
        entries = [entry for entry in entries if _score_index_entry(entry, query)[0] > 0 or _score_index_entry_semantic(entry, query) > 0.08]
        entries.sort(
            key=lambda entry: (
                _score_index_entry(entry, query)[0] + _score_index_entry_semantic(entry, query) * 12.0,
                entry.confidence,
                entry.updated_at,
            ),
            reverse=True,
        )
    else:
        entries.sort(key=lambda entry: (entry.category, entry.folder_path or "", entry.file_path, entry.entry_type, entry.title))
    total = len(entries)
    return KnowledgeIndexListResponse(
        entries=entries[request.offset : request.offset + request.limit],
        total=total,
        offset=request.offset,
        limit=request.limit,
    )


def get_knowledge_index_entry(index_id: str, *, user_id: str | None = None) -> KnowledgeIndexEntry:
    for entry in get_knowledge_storage().list_indexes(user_id=user_id):
        if entry.index_id == index_id:
            return entry
    raise KeyError(index_id)


def create_knowledge_index_entry(request: KnowledgeIndexEntryCreate, *, user_id: str | None = None) -> KnowledgeIndexEntry:
    storage = get_knowledge_storage()
    indexes = storage.list_indexes(user_id=user_id)
    timestamp = now_iso()
    folder_path = request.folder_path
    if folder_path is None:
        parent = Path(request.file_path).parent
        folder_path = "" if str(parent) == "." else parent.as_posix()
    entry = KnowledgeIndexEntry(
        index_id=f"idx_{uuid.uuid4().hex}",
        title=request.title.strip(),
        entry_type=request.entry_type,
        category=request.category.strip(),
        file_path=Path(request.file_path).as_posix(),
        folder_path=folder_path,
        domain=request.domain,
        authority=request.authority,
        document_type=request.document_type,
        year=request.year,
        keywords=request.keywords,
        technical_terms=request.technical_terms,
        methods=request.methods,
        research_objects=request.research_objects,
        proposal_sections=request.proposal_sections,
        evidence_type=request.evidence_type,
        evidence_id=request.evidence_id,
        asset_ids=request.asset_ids,
        applicant_id=request.applicant_id,
        verification_status=request.verification_status,
        valid_from=request.valid_from,
        valid_to=request.valid_to,
        source_file_path=request.source_file_path,
        source_anchor=request.source_anchor,
        chunk_file_path=request.chunk_file_path,
        summary=request.summary,
        recommended_sections=request.recommended_sections,
        applicable_chapters=request.applicable_chapters,
        project_types=request.project_types,
        source_document_id=request.source_document_id,
        metadata=request.metadata,
        confidence=request.confidence,
        confidentiality_level=request.confidentiality_level,
        created_at=timestamp,
        updated_at=timestamp,
    )
    indexes.append(entry)
    storage.save_all_indexes(indexes, user_id=user_id)
    return entry


def update_knowledge_index_entry(
    index_id: str,
    request: KnowledgeIndexEntryPatch,
    *,
    user_id: str | None = None,
) -> KnowledgeIndexEntry:
    storage = get_knowledge_storage()
    indexes = storage.list_indexes(user_id=user_id)
    updated: KnowledgeIndexEntry | None = None
    patch = request.model_dump(exclude_unset=True)
    if "file_path" in patch and patch["file_path"] is not None:
        patch["file_path"] = Path(patch["file_path"]).as_posix()

    for index, entry in enumerate(indexes):
        if entry.index_id != index_id:
            continue
        data = entry.model_dump()
        data.update(patch)
        data["updated_at"] = now_iso()
        updated = KnowledgeIndexEntry(**data)
        indexes[index] = updated
        break

    if updated is None:
        raise KeyError(index_id)

    storage.save_all_indexes(indexes, user_id=user_id)
    return updated


def delete_knowledge_index_entry(index_id: str, *, user_id: str | None = None) -> None:
    storage = get_knowledge_storage()
    indexes = storage.list_indexes(user_id=user_id)
    kept = [entry for entry in indexes if entry.index_id != index_id]
    if len(kept) == len(indexes):
        raise KeyError(index_id)
    storage.save_all_indexes(kept, user_id=user_id)


def _list_search_index_candidates(
    request: KnowledgeIndexSearchRequest,
    *,
    user_id: str | None = None,
) -> list[KnowledgeIndexEntry]:
    try:
        entries = search_sqlite_knowledge_index_candidates(
            request,
            root=_knowledge_root_path(user_id=user_id),
        )
    except Exception:
        logger.warning("Failed to search SQLite knowledge index; falling back to JSON.", exc_info=True)
        entries = None
    if entries is not None:
        return entries
    return get_knowledge_storage().list_indexes(user_id=user_id)


def search_knowledge_index_entries(
    request: KnowledgeIndexSearchRequest,
    *,
    user_id: str | None = None,
) -> KnowledgeIndexSearchResponse:
    expanded_request = expand_knowledge_index_search_request(request)
    has_expanded_query = expanded_request.query != request.query
    lexical_queries = _lexical_queries(request, expanded_request.query)
    candidate_query = " ".join(query for query, _ in lexical_queries)
    candidate_request = expanded_request.model_copy(update={"query": candidate_query})
    entries = _list_search_index_candidates(candidate_request, user_id=user_id)
    results: list[KnowledgeIndexSearchResult] = []

    semantic_enabled = expanded_request.search_mode in {"hybrid", "semantic"}
    keyword_enabled = expanded_request.search_mode in {"hybrid", "keyword"}

    for entry in entries:
        if expanded_request.entry_types and entry.entry_type not in expanded_request.entry_types:
            continue
        if expanded_request.categories and entry.category not in expanded_request.categories:
            continue
        if expanded_request.domains and (entry.domain is None or entry.domain not in expanded_request.domains):
            continue
        searchable_chapters = entry.proposal_sections or entry.applicable_chapters
        if expanded_request.applicable_chapters and not _list_intersects(searchable_chapters, expanded_request.applicable_chapters):
            continue
        if expanded_request.project_types and not _list_intersects(entry.project_types, expanded_request.project_types):
            continue
        if expanded_request.authorities and not _optional_text_matches(entry.authority, expanded_request.authorities):
            continue
        if expanded_request.document_types and not _optional_text_matches(entry.document_type, expanded_request.document_types):
            continue
        if expanded_request.years and entry.year not in expanded_request.years:
            continue
        if not _entry_valid_on(entry, expanded_request.valid_on):
            continue
        if expanded_request.applicant_ids and entry.applicant_id not in expanded_request.applicant_ids:
            continue
        if expanded_request.evidence_types and entry.evidence_type not in expanded_request.evidence_types:
            continue
        if expanded_request.verification_statuses and entry.verification_status not in expanded_request.verification_statuses:
            continue
        if not expanded_request.include_restricted and entry.confidentiality_level == "restricted":
            continue
        if any(not _metadata_value_matches(entry.metadata.get(key), value) for key, value in expanded_request.metadata_filters.items()):
            continue

        score = 0.0
        expanded_score = 0.0
        matched_fields: list[str] = []
        matched_queries: list[str] = []
        if keyword_enabled:
            for lexical_query, weight in lexical_queries:
                lexical_score, lexical_fields = _score_index_entry(entry, lexical_query)
                if lexical_score <= 0:
                    continue
                weighted_score = lexical_score * weight
                score += weighted_score
                expanded_score = max(expanded_score, weighted_score)
                matched_queries.append(lexical_query)
                matched_fields.extend(field for field in lexical_fields if field not in matched_fields)

        semantic_score = 0.0
        if semantic_enabled:
            semantic_query = expanded_request.query if has_expanded_query else request.query
            semantic_score = _score_index_entry_semantic(entry, semantic_query)
            if semantic_score > 0.08 and "semantic_vector" not in matched_fields:
                matched_fields.append("semantic_vector")

        combined_score = score + (semantic_score * expanded_request.semantic_weight)
        if expanded_request.query and max(score, expanded_score, semantic_score) <= 0:
            continue
        results.append(
            KnowledgeIndexSearchResult(
                entry=entry,
                score=combined_score,
                matched_fields=matched_fields,
                matched_queries=matched_queries,
            )
        )

    results.sort(key=lambda result: (result.score, result.entry.confidence, result.entry.updated_at), reverse=True)
    limited = [
        KnowledgeIndexSearchResult(
            entry=result.entry,
            score=_bounded_index_search_score(result.score),
            matched_fields=result.matched_fields,
            matched_queries=result.matched_queries,
        )
        for result in results[: expanded_request.limit]
    ]
    return KnowledgeIndexSearchResponse(results=limited, count=len(limited))


def search_knowledge_index_entries_combined(
    request: KnowledgeIndexSearchRequest,
    *,
    user_id: str,
) -> KnowledgeIndexSearchResponse:
    """Search the caller's private library and the server public library.

    Each underlying search applies the same filters and score normalization.
    Results retain their source scope so a subsequent read can resolve the
    relative file path against the correct physical root.
    """
    private_response = search_knowledge_index_entries(request, user_id=user_id)
    if _knowledge_root_path(user_id=user_id) == _knowledge_root_path(user_id=None):
        return private_response
    public_response = search_knowledge_index_entries(request, user_id=None)
    combined = [
        result.model_copy(update={"scope": "private"})
        for result in private_response.results
    ]
    combined.extend(
        result.model_copy(update={"scope": "public"})
        for result in public_response.results
    )
    combined.sort(
        key=lambda result: (
            result.score,
            result.scope == "private",
            result.entry.confidence,
            result.entry.updated_at,
        ),
        reverse=True,
    )
    limited = combined[: request.limit]
    return KnowledgeIndexSearchResponse(results=limited, count=len(limited))


def _entry_matches_recall_case(entry: KnowledgeIndexEntry, case: KnowledgeRecallEvalCase) -> bool:
    expected_paths = {Path(path).as_posix() for path in case.expected_file_paths}
    candidate_paths = {
        entry.file_path,
        entry.source_file_path or "",
        entry.chunk_file_path or "",
        str(entry.metadata.get("source_file_path") or ""),
    }
    if expected_paths and any(path in candidate_paths for path in expected_paths):
        return True
    if case.expected_index_ids and entry.index_id in set(case.expected_index_ids):
        return True
    if case.expected_categories and entry.category in set(case.expected_categories):
        return True
    return False


def evaluate_knowledge_recall(
    request: KnowledgeRecallEvalRequest,
    *,
    user_id: str | None = None,
) -> KnowledgeRecallEvalResponse:
    case_results: list[KnowledgeRecallEvalCaseResult] = []
    for case in request.cases:
        expected_count = len(case.expected_file_paths) + len(case.expected_index_ids) + len(case.expected_categories)
        search_response = search_knowledge_index_entries(
            KnowledgeIndexSearchRequest(
                query=case.query,
                query_variants=case.query_variants,
                entry_types=case.entry_types,
                categories=case.categories or ([request.category] if request.category else None),
                applicable_chapters=case.applicable_chapters,
                domains=case.domains,
                project_types=case.project_types,
                authorities=case.authorities,
                document_types=case.document_types,
                years=case.years,
                valid_on=case.valid_on,
                applicant_ids=case.applicant_ids,
                limit=request.limit,
                search_mode=request.search_mode,
            ),
            user_id=user_id,
        )
        first_rank: int | None = None
        for rank, result in enumerate(search_response.results, start=1):
            if _entry_matches_recall_case(result.entry, case):
                first_rank = rank
                break
        reciprocal_rank = 0.0 if first_rank is None else 1.0 / first_rank
        forbidden_paths = {Path(path).as_posix() for path in case.forbidden_file_paths}
        forbidden_hits: list[str] = []
        for result in search_response.results:
            candidate_paths = {
                result.entry.file_path,
                result.entry.source_file_path or "",
                result.entry.chunk_file_path or "",
                str(result.entry.metadata.get("source_file_path") or ""),
            }
            forbidden_hits.extend(path for path in forbidden_paths if path in candidate_paths and path not in forbidden_hits)
        case_results.append(
            KnowledgeRecallEvalCaseResult(
                query=case.query,
                expected_count=expected_count,
                hit=first_rank is not None,
                first_rank=first_rank,
                reciprocal_rank=reciprocal_rank,
                forbidden_hits=forbidden_hits,
                top_results=search_response.results,
            )
        )
    total_cases = len(case_results)
    hit_count = sum(1 for item in case_results if item.hit)
    mrr = sum(item.reciprocal_rank for item in case_results) / total_cases if total_cases else 0.0
    forbidden_hit_count = sum(len(item.forbidden_hits) for item in case_results)
    forbidden_path_count = sum(len(case.forbidden_file_paths) for case in request.cases)
    return KnowledgeRecallEvalResponse(
        cases=case_results,
        total_cases=total_cases,
        hit_count=hit_count,
        recall_at_k=(hit_count / total_cases if total_cases else 0.0),
        mrr=mrr,
        forbidden_hit_count=forbidden_hit_count,
        contamination_rate=(forbidden_hit_count / forbidden_path_count if forbidden_path_count else 0.0),
    )


def read_knowledge_file(request: KnowledgeFileReadRequest, *, user_id: str | None = None) -> KnowledgeFileReadResponse:
    path = _resolve_knowledge_file(request.file_path, user_id=user_id)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(request.file_path)

    content = extract_text(path)
    if request.anchor:
        section = _extract_markdown_section(content, request.anchor)
        if section:
            content = section

    truncated = len(content) > request.max_chars
    if truncated:
        content = content[: request.max_chars]

    return KnowledgeFileReadResponse(
        file_path=Path(request.file_path).as_posix(),
        resolved_path=str(path),
        anchor=request.anchor,
        content=content,
        truncated=truncated,
    )


def read_knowledge_file_combined(
    request: KnowledgeFileReadRequest,
    *,
    user_id: str,
    scope: str = "auto",
) -> KnowledgeFileReadResponse:
    """Read from a selected scope, or prefer private then fall back to public."""
    if scope not in {"auto", "private", "public"}:
        raise ValueError("scope must be one of: auto, private, public")
    if scope == "public":
        return read_knowledge_file(request, user_id=None).model_copy(update={"scope": "public"})
    if scope == "private":
        return read_knowledge_file(request, user_id=user_id).model_copy(update={"scope": "private"})
    try:
        return read_knowledge_file(request, user_id=user_id).model_copy(update={"scope": "private"})
    except FileNotFoundError:
        return read_knowledge_file(request, user_id=None).model_copy(update={"scope": "public"})


def save_knowledge_file(request: KnowledgeFileSaveRequest, *, user_id: str | None = None) -> KnowledgeFileSaveResponse:
    path = _resolve_knowledge_file(request.file_path, user_id=user_id)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(request.file_path)

    suffix = path.suffix.lower()
    if suffix not in _EDITABLE_KNOWLEDGE_EXTENSIONS:
        raise ValueError("Only markdown and plain-text knowledge files can be edited online.")

    next_content = request.content
    if request.anchor:
        if suffix not in {".md", ".markdown"}:
            raise ValueError("Anchored edits are only supported for markdown files.")
        current_content = path.read_text(encoding="utf-8")
        next_content = _replace_markdown_section(current_content, request.anchor, request.content)

    _atomic_write_text(path, next_content)
    return KnowledgeFileSaveResponse(
        file_path=Path(request.file_path).as_posix(),
        resolved_path=str(path),
        anchor=request.anchor,
        bytes_written=len(next_content.encode("utf-8")),
        saved=True,
    )
