"""SQLite sidecar index for knowledge-base search."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deerflow.config import get_app_config
from deerflow.knowledge.content_store import load_index_entry_content
from deerflow.knowledge.embeddings import (
    LOCAL_HASH_SIGNATURE,
    configured_embedding_signature,
    embed_documents_with_signature,
    embed_query_for_signature,
    embed_texts_locally,
)
from deerflow.knowledge.schemas import KnowledgeIndexEntry, KnowledgeIndexSearchRequest
from deerflow.knowledge.vector_search import cosine_similarity

_SCHEMA_VERSION = "4"
_INDEX_DIR = ".index"
_INDEX_FILENAME = "knowledge.sqlite3"
_MAX_CANDIDATES = 5000
_MIN_CANDIDATES = 500
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[0-9A-Za-z_\-\u4e00-\u9fff]+")
_FTS_BM25_WEIGHTS = (0.0, 10.0, 5.0, 4.0, 7.0, 6.0, 5.0, 5.0, 8.0, 4.0, 8.0, 2.0, 2.0, 2.0, 4.0, 3.0)


@dataclass(frozen=True)
class KnowledgeIndexCandidate:
    """An index entry plus retrieval-only content and semantic score."""

    entry: KnowledgeIndexEntry
    content_text: str = ""
    semantic_score: float = 0.0


def sqlite_knowledge_index_path(root: Path) -> Path:
    """Return the SQLite sidecar path under a knowledge-base root."""

    return root / _INDEX_DIR / _INDEX_FILENAME


def sqlite_knowledge_index_exists(root: Path) -> bool:
    return sqlite_knowledge_index_path(root).exists()


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA temp_store=MEMORY")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS index_entries (
            index_id TEXT PRIMARY KEY,
            entry_json TEXT NOT NULL,
            title TEXT NOT NULL,
            entry_type TEXT NOT NULL,
            category TEXT NOT NULL,
            domain TEXT,
            authority TEXT,
            document_type TEXT,
            year INTEGER,
            applicant_id TEXT,
            verification_status TEXT,
            valid_from TEXT,
            valid_to TEXT,
            file_path TEXT NOT NULL,
            source_file_path TEXT,
            source_anchor TEXT,
            confidentiality_level TEXT NOT NULL,
            confidence REAL NOT NULL,
            updated_at TEXT NOT NULL,
            search_text TEXT NOT NULL,
            content_text TEXT NOT NULL DEFAULT '',
            embedding_fingerprint TEXT NOT NULL DEFAULT '',
            semantic_vector TEXT
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(index_entries)").fetchall()}
    column_migrations = {
        "semantic_vector": "TEXT",
        "authority": "TEXT",
        "document_type": "TEXT",
        "year": "INTEGER",
        "applicant_id": "TEXT",
        "verification_status": "TEXT",
        "valid_from": "TEXT",
        "valid_to": "TEXT",
        "content_text": "TEXT NOT NULL DEFAULT ''",
        "embedding_fingerprint": "TEXT NOT NULL DEFAULT ''",
    }
    for column, data_type in column_migrations.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE index_entries ADD COLUMN {column} {data_type}")
    version_row = connection.execute("SELECT value FROM metadata WHERE key = ?", ("schema_version",)).fetchone()
    if version_row is None or version_row["value"] != _SCHEMA_VERSION:
        rows = connection.execute("SELECT index_id, entry_json FROM index_entries").fetchall()
        for row in rows:
            try:
                payload = json.loads(row["entry_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            connection.execute(
                """
                UPDATE index_entries
                SET authority = ?, document_type = ?, year = ?, applicant_id = ?,
                    verification_status = ?, valid_from = ?, valid_to = ?
                WHERE index_id = ?
                """,
                (
                    payload.get("authority"),
                    payload.get("document_type"),
                    payload.get("year"),
                    payload.get("applicant_id"),
                    payload.get("verification_status"),
                    payload.get("valid_from"),
                    payload.get("valid_to"),
                    row["index_id"],
                ),
            )
    fts_columns = {row["name"] for row in connection.execute("PRAGMA table_info(index_entries_fts)").fetchall()}
    rebuild_fts = bool(fts_columns and "content" not in fts_columns)
    if rebuild_fts:
        connection.execute("DROP TABLE index_entries_fts")
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS index_entries_fts USING fts5(
            index_id UNINDEXED,
            title,
            category,
            domain,
            keywords,
            technical_terms,
            methods,
            research_objects,
            proposal_sections,
            evidence_type,
            source_anchor,
            source_file_path,
            summary,
            file_path,
            project_types,
            content
        )
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("schema_version", _SCHEMA_VERSION),
    )
    if rebuild_fts:
        rows = connection.execute("SELECT entry_json, content_text FROM index_entries").fetchall()
        for row in rows:
            try:
                entry = KnowledgeIndexEntry(**json.loads(row["entry_json"]))
            except (TypeError, json.JSONDecodeError, ValueError):
                continue
            _insert_fts_entry(connection, entry, _entry_search_columns(entry, str(row["content_text"] or "")))


def _join(values: Iterable[Any]) -> str:
    return " ".join(str(value) for value in values if value is not None)


def _entry_payload(entry: KnowledgeIndexEntry) -> dict[str, Any]:
    payload = entry.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    payload["entry_type"] = entry.entry_type
    return payload


def _entry_search_columns(entry: KnowledgeIndexEntry, content_text: str = "") -> dict[str, str]:
    return {
        "title": entry.title,
        "category": entry.category,
        "domain": entry.domain or "",
        "authority": entry.authority or "",
        "document_type": entry.document_type or "",
        "year": str(entry.year or ""),
        "keywords": _join(entry.keywords),
        "technical_terms": _join(entry.technical_terms),
        "methods": _join(entry.methods),
        "research_objects": _join(entry.research_objects),
        "proposal_sections": _join([*entry.proposal_sections, *entry.applicable_chapters]),
        "evidence_type": entry.evidence_type or "",
        "source_anchor": entry.source_anchor or "",
        "source_file_path": entry.source_file_path or "",
        "summary": entry.summary,
        "file_path": entry.file_path,
        "project_types": _join(entry.project_types),
        "content": content_text,
    }


def _entry_search_text(entry: KnowledgeIndexEntry, content_text: str = "") -> str:
    metadata_text = json.dumps(entry.metadata, ensure_ascii=False, sort_keys=True)
    recommended_text = json.dumps(
        [section.model_dump(mode="json", exclude_none=True) for section in entry.recommended_sections],
        ensure_ascii=False,
        sort_keys=True,
    )
    values = [*_entry_search_columns(entry, content_text).values(), metadata_text, recommended_text]
    return " ".join(value for value in values if value).lower()


def _entry_embedding_text(entry: KnowledgeIndexEntry, content_text: str = "") -> str:
    """Return stable semantic input without parser/build bookkeeping fields."""

    semantic_metadata = {key: value for key, value in entry.metadata.items() if not key.startswith(("source_", "chunk_", "parser")) and key not in {"indexer_version", "char_count", "heading_path", "primary_section"}}
    recommended_text = json.dumps(
        [section.model_dump(mode="json", exclude_none=True) for section in entry.recommended_sections],
        ensure_ascii=False,
        sort_keys=True,
    )
    values = [
        *_entry_search_columns(entry, content_text).values(),
        json.dumps(semantic_metadata, ensure_ascii=False, sort_keys=True),
        recommended_text,
    ]
    return " ".join(value for value in values if value).lower()


def _embedding_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _decode_vector(raw_vector: Any) -> list[float] | None:
    if not raw_vector:
        return None
    try:
        vector = json.loads(raw_vector)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(vector, list) or not vector:
        return None
    try:
        return [float(value) for value in vector]
    except (TypeError, ValueError):
        return None


def _insert_fts_entry(connection: sqlite3.Connection, entry: KnowledgeIndexEntry, columns: dict[str, str]) -> None:
    connection.execute(
        """
        INSERT INTO index_entries_fts(
            index_id,
            title,
            category,
            domain,
            keywords,
            technical_terms,
            methods,
            research_objects,
            proposal_sections,
            evidence_type,
            source_anchor,
            source_file_path,
            summary,
            file_path,
            project_types,
            content
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.index_id,
            columns["title"],
            columns["category"],
            columns["domain"],
            columns["keywords"],
            columns["technical_terms"],
            columns["methods"],
            columns["research_objects"],
            columns["proposal_sections"],
            columns["evidence_type"],
            columns["source_anchor"],
            columns["source_file_path"],
            columns["summary"],
            columns["file_path"],
            columns["project_types"],
            columns["content"],
        ),
    )


def sync_sqlite_knowledge_index(entries: Iterable[KnowledgeIndexEntry], *, root: Path) -> dict[str, Any]:
    """Replace the sidecar while reusing vectors whose semantic input is unchanged."""

    entry_list = list(entries)
    path = sqlite_knowledge_index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    content_max_chars = get_app_config().knowledge_retrieval.content_max_chars
    prepared: list[tuple[KnowledgeIndexEntry, str, str, str, str]] = []
    for entry in entry_list:
        content_text = load_index_entry_content(root, entry, max_chars=content_max_chars)
        search_text = _entry_search_text(entry, content_text)
        embedding_text = _entry_embedding_text(entry, content_text)
        prepared.append(
            (
                entry,
                content_text,
                search_text,
                embedding_text,
                _embedding_fingerprint(embedding_text),
            )
        )
    desired_signature = configured_embedding_signature()
    reused_count = 0
    generated_count = 0

    with _connect(path) as connection:
        _ensure_schema(connection)
        signature_row = connection.execute(
            "SELECT value FROM metadata WHERE key = ?",
            ("embedding_signature",),
        ).fetchone()
        existing_signature = str(signature_row["value"]) if signature_row else ""
        reusable_vectors: dict[str, tuple[str, list[float]]] = {}
        if existing_signature == desired_signature:
            rows = connection.execute("SELECT index_id, embedding_fingerprint, semantic_vector FROM index_entries").fetchall()
            for row in rows:
                vector = _decode_vector(row["semantic_vector"])
                fingerprint = str(row["embedding_fingerprint"] or "")
                if vector is not None and fingerprint:
                    reusable_vectors[str(row["index_id"])] = (fingerprint, vector)

        vectors_by_id: dict[str, list[float]] = {}
        pending: list[tuple[str, str]] = []
        for entry, _, _, embedding_text, fingerprint in prepared:
            reusable = reusable_vectors.get(entry.index_id)
            if reusable is not None and reusable[0] == fingerprint:
                vectors_by_id[entry.index_id] = reusable[1]
                reused_count += 1
            else:
                pending.append((entry.index_id, embedding_text))

        embedding_signature = desired_signature
        if pending:
            pending_vectors, embedding_signature = embed_documents_with_signature([embedding_text for _, embedding_text in pending])
            if embedding_signature == desired_signature:
                for (index_id, _), vector in zip(pending, pending_vectors, strict=True):
                    vectors_by_id[index_id] = vector
                generated_count = len(pending)
            else:
                # A provider failure changes the vector space. Rebuild every
                # vector locally rather than mixing remote and fallback vectors.
                local_vectors = pending_vectors if len(pending) == len(prepared) else embed_texts_locally([item[3] for item in prepared])
                vectors_by_id = {item[0].index_id: vector for item, vector in zip(prepared, local_vectors, strict=True)}
                embedding_signature = LOCAL_HASH_SIGNATURE
                reused_count = 0
                generated_count = len(prepared)

        connection.execute("DELETE FROM index_entries")
        connection.execute("DELETE FROM index_entries_fts")
        connection.executemany(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
            (
                ("embedding_signature", embedding_signature),
                ("embedding_configured_signature", desired_signature),
                ("embedding_reused_count", str(reused_count)),
                ("embedding_generated_count", str(generated_count)),
                ("embedding_fallback", "1" if embedding_signature != desired_signature else "0"),
            ),
        )
        for entry, content_text, search_text, _, fingerprint in prepared:
            vector = vectors_by_id[entry.index_id]
            payload = _entry_payload(entry)
            columns = _entry_search_columns(entry, content_text)
            connection.execute(
                """
                INSERT INTO index_entries(
                    index_id,
                    entry_json,
                    title,
                    entry_type,
                    category,
                    domain,
                    authority,
                    document_type,
                    year,
                    applicant_id,
                    verification_status,
                    valid_from,
                    valid_to,
                    file_path,
                    source_file_path,
                    source_anchor,
                    confidentiality_level,
                    confidence,
                    updated_at,
                    search_text,
                    content_text,
                    embedding_fingerprint,
                    semantic_vector
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.index_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    entry.title,
                    entry.entry_type,
                    entry.category,
                    entry.domain,
                    entry.authority,
                    entry.document_type,
                    entry.year,
                    entry.applicant_id,
                    entry.verification_status,
                    entry.valid_from,
                    entry.valid_to,
                    entry.file_path,
                    entry.source_file_path,
                    entry.source_anchor,
                    entry.confidentiality_level,
                    entry.confidence,
                    entry.updated_at,
                    search_text,
                    content_text,
                    fingerprint,
                    json.dumps(vector, separators=(",", ":")),
                ),
            )
            _insert_fts_entry(connection, entry, columns)
        connection.commit()

    return {
        "path": str(path),
        "entries": len(entry_list),
        "bytes": path.stat().st_size if path.exists() else 0,
        "embedding_signature": embedding_signature,
        "embedding_configured_signature": desired_signature,
        "embedding_reused_count": reused_count,
        "embedding_generated_count": generated_count,
        "embedding_fallback": embedding_signature != desired_signature,
    }


def sqlite_knowledge_index_stats(root: Path) -> dict[str, Any]:
    """Return persisted vector-build status without exposing provider secrets."""

    path = sqlite_knowledge_index_path(root)
    if not path.exists():
        return {}
    with _connect(path) as connection:
        _ensure_schema(connection)
        rows = connection.execute("SELECT key, value FROM metadata WHERE key LIKE 'embedding_%'").fetchall()
        values = {str(row["key"]): str(row["value"]) for row in rows}
        entry_row = connection.execute("SELECT COUNT(*) AS count FROM index_entries").fetchone()
    return {
        "embedding_signature": values.get("embedding_signature", ""),
        "embedding_configured_signature": values.get("embedding_configured_signature", ""),
        "embedding_reused_count": int(values.get("embedding_reused_count", "0")),
        "embedding_generated_count": int(values.get("embedding_generated_count", "0")),
        "embedding_fallback": values.get("embedding_fallback", "0") == "1",
        "embedding_entries": int(entry_row["count"]) if entry_row else 0,
    }


def sqlite_knowledge_content_map(root: Path) -> dict[str, str]:
    """Return already-extracted bodies for post-build quality checks."""

    path = sqlite_knowledge_index_path(root)
    if not path.exists():
        return {}
    with _connect(path) as connection:
        _ensure_schema(connection)
        rows = connection.execute("SELECT index_id, content_text FROM index_entries").fetchall()
    return {str(row["index_id"]): str(row["content_text"] or "") for row in rows}


def _candidate_limit(request_limit: int) -> int:
    return min(_MAX_CANDIDATES, max(_MIN_CANDIDATES, request_limit * 50))


def _query_terms(query: str) -> list[str]:
    lower = query.lower().strip()
    if not lower:
        return []

    terms: list[str] = []
    for term in re.split(r"\s+", lower):
        cleaned = term.strip()
        if cleaned and cleaned not in terms:
            terms.append(cleaned)

    for chunk in _CJK_RE.findall(lower):
        if len(chunk) < 3:
            continue
        for length in range(min(8, len(chunk)), 2, -1):
            for start in range(0, len(chunk) - length + 1):
                gram = chunk[start : start + length]
                if gram not in terms:
                    terms.append(gram)
        if chunk not in terms:
            terms.append(chunk)

    return terms[:80]


def _fts_query(query: str) -> str:
    words = []
    for match in _WORD_RE.finditer(query.lower()):
        word = match.group(0).strip("-_")
        if not word:
            continue
        escaped = word.replace('"', '""')
        phrase = f'"{escaped}"'
        if phrase not in words:
            words.append(phrase)
    return " OR ".join(words[:40])


def _sql_in_clause(column: str, values: Sequence[str]) -> tuple[str, list[str]]:
    placeholders = ",".join("?" for _ in values)
    return f"{column} IN ({placeholders})", list(values)


def _base_filters(request: KnowledgeIndexSearchRequest) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if request.entry_types:
        clause, values = _sql_in_clause("e.entry_type", request.entry_types)
        clauses.append(clause)
        params.extend(values)
    if request.categories:
        clause, values = _sql_in_clause("e.category", request.categories)
        clauses.append(clause)
        params.extend(values)
    if request.domains:
        clause, values = _sql_in_clause("e.domain", request.domains)
        clauses.append(clause)
        params.extend(values)
    if request.authorities:
        clause, values = _sql_in_clause("e.authority", request.authorities)
        clauses.append(clause)
        params.extend(values)
    if request.document_types:
        clause, values = _sql_in_clause("e.document_type", request.document_types)
        clauses.append(clause)
        params.extend(values)
    if request.years:
        placeholders = ",".join("?" for _ in request.years)
        clauses.append(f"e.year IN ({placeholders})")
        params.extend(request.years)
    if request.applicant_ids:
        clause, values = _sql_in_clause("e.applicant_id", request.applicant_ids)
        clauses.append(clause)
        params.extend(values)
    if request.verification_statuses:
        clause, values = _sql_in_clause("e.verification_status", request.verification_statuses)
        clauses.append(clause)
        params.extend(values)
    if request.valid_on:
        target = request.valid_on.strip()[:10]
        clauses.append("(e.valid_from IS NULL OR substr(e.valid_from, 1, 10) <= ?)")
        clauses.append("(e.valid_to IS NULL OR substr(e.valid_to, 1, 10) >= ?)")
        params.extend([target, target])
    if not request.include_restricted:
        clauses.append("e.confidentiality_level != ?")
        params.append("restricted")

    return clauses, params


def _where_sql(clauses: list[str], *, prefix: str = "WHERE") -> str:
    if not clauses:
        return ""
    return f"{prefix} " + " AND ".join(clauses)


def _rows_to_candidates(rows: Iterable[sqlite3.Row]) -> list[KnowledgeIndexCandidate]:
    candidates: list[KnowledgeIndexCandidate] = []
    seen: set[str] = set()
    for row in rows:
        index_id = str(row["index_id"])
        if index_id in seen:
            continue
        seen.add(index_id)
        candidates.append(
            KnowledgeIndexCandidate(
                entry=KnowledgeIndexEntry(**json.loads(row["entry_json"])),
                content_text=str(row["content_text"] or ""),
            )
        )
    return candidates


def _fetch_fts_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexCandidate]:
    match_query = _fts_query(request.query)
    if not match_query:
        return []

    clauses, params = _base_filters(request)
    clauses.append("index_entries_fts MATCH ?")
    params.append(match_query)
    params.append(limit)
    where_sql = _where_sql(clauses)
    weights = ", ".join(str(weight) for weight in _FTS_BM25_WEIGHTS)
    rows = connection.execute(
        f"""
        SELECT e.index_id, e.entry_json, e.content_text
        FROM index_entries e
        JOIN index_entries_fts ON e.index_id = index_entries_fts.index_id
        {where_sql}
        ORDER BY bm25(index_entries_fts, {weights}), e.confidence DESC, e.updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return _rows_to_candidates(rows)


def _fetch_like_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexCandidate]:
    clauses, params = _base_filters(request)
    terms = _query_terms(request.query)
    if terms:
        like_clauses = []
        for term in terms:
            like_clauses.append("e.search_text LIKE ?")
            params.append(f"%{term}%")
        clauses.append("(" + " OR ".join(like_clauses) + ")")

    params.append(limit)
    where_sql = _where_sql(clauses)
    rows = connection.execute(
        f"""
        SELECT e.index_id, e.entry_json, e.content_text
        FROM index_entries e
        {where_sql}
        ORDER BY e.confidence DESC, e.updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return _rows_to_candidates(rows)


def _fetch_semantic_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexCandidate]:
    if not request.query.strip():
        return []

    signature_row = connection.execute(
        "SELECT value FROM metadata WHERE key = ?",
        ("embedding_signature",),
    ).fetchone()
    signature = str(signature_row["value"]) if signature_row else ""
    query_vector = embed_query_for_signature(request.query, signature)
    if query_vector is None:
        return []
    clauses, params = _base_filters(request)
    where_sql = _where_sql(clauses)
    rows = connection.execute(
        f"""
        SELECT e.index_id, e.entry_json, e.content_text, e.semantic_vector
        FROM index_entries e
        {where_sql}
        """,
        params,
    ).fetchall()

    scored: list[tuple[float, sqlite3.Row]] = []
    for row in rows:
        raw_vector = row["semantic_vector"]
        if not raw_vector:
            continue
        try:
            vector = json.loads(raw_vector)
        except json.JSONDecodeError:
            continue
        if not isinstance(vector, list):
            continue
        similarity = cosine_similarity(query_vector, [float(value) for value in vector])
        if similarity <= get_app_config().knowledge_retrieval.semantic_min_similarity:
            continue
        scored.append((similarity, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    candidates: list[KnowledgeIndexCandidate] = []
    for similarity, row in scored[:limit]:
        candidates.append(
            KnowledgeIndexCandidate(
                entry=KnowledgeIndexEntry(**json.loads(row["entry_json"])),
                content_text=str(row["content_text"] or ""),
                semantic_score=similarity,
            )
        )
    return candidates


def search_sqlite_knowledge_index_candidates(
    request: KnowledgeIndexSearchRequest,
    *,
    root: Path,
) -> list[KnowledgeIndexCandidate] | None:
    """Return SQLite-backed candidates, or None when the sidecar is unavailable."""

    path = sqlite_knowledge_index_path(root)
    if not path.exists():
        return None

    limit = _candidate_limit(request.limit)
    with _connect(path) as connection:
        _ensure_schema(connection)
        if not request.query.strip():
            return _fetch_like_entries(connection, request, limit=limit)

        entries: list[KnowledgeIndexCandidate] = []
        positions: dict[str, int] = {}
        try:
            fts_entries = _fetch_fts_entries(connection, request, limit=limit)
        except sqlite3.Error:
            fts_entries = []
        like_entries = _fetch_like_entries(connection, request, limit=limit)
        semantic_entries = [] if request.search_mode == "keyword" else _fetch_semantic_entries(connection, request, limit=limit)
        if request.search_mode == "semantic":
            ordered_sources = [*semantic_entries, *fts_entries, *like_entries]
        else:
            ordered_sources = [*fts_entries, *like_entries, *semantic_entries]
        for candidate in ordered_sources:
            entry_id = candidate.entry.index_id
            if entry_id in positions:
                position = positions[entry_id]
                if candidate.semantic_score > entries[position].semantic_score:
                    entries[position] = KnowledgeIndexCandidate(
                        entry=entries[position].entry,
                        content_text=entries[position].content_text or candidate.content_text,
                        semantic_score=candidate.semantic_score,
                    )
                continue
            positions[entry_id] = len(entries)
            entries.append(candidate)
        return entries
