"""SQLite sidecar index for knowledge-base search."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from deerflow.knowledge.schemas import KnowledgeIndexEntry, KnowledgeIndexSearchRequest
from deerflow.knowledge.vector_search import cosine_similarity, embed_text

_SCHEMA_VERSION = "2"
_INDEX_DIR = ".index"
_INDEX_FILENAME = "knowledge.sqlite3"
_MAX_CANDIDATES = 5000
_MIN_CANDIDATES = 500
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[0-9A-Za-z_\-\u4e00-\u9fff]+")
_FTS_BM25_WEIGHTS = (0.0, 10.0, 5.0, 4.0, 7.0, 6.0, 5.0, 5.0, 8.0, 4.0, 8.0, 2.0, 2.0, 2.0, 4.0)


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
            project_types
        )
        """
    )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        ("schema_version", _SCHEMA_VERSION),
    )


def _join(values: Iterable[Any]) -> str:
    return " ".join(str(value) for value in values if value is not None)


def _entry_payload(entry: KnowledgeIndexEntry) -> dict[str, Any]:
    payload = entry.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
    payload["entry_type"] = entry.entry_type
    return payload


def _entry_search_columns(entry: KnowledgeIndexEntry) -> dict[str, str]:
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
    }


def _entry_search_text(entry: KnowledgeIndexEntry) -> str:
    metadata_text = json.dumps(entry.metadata, ensure_ascii=False, sort_keys=True)
    recommended_text = json.dumps(
        [section.model_dump(mode="json", exclude_none=True) for section in entry.recommended_sections],
        ensure_ascii=False,
        sort_keys=True,
    )
    values = [*_entry_search_columns(entry).values(), metadata_text, recommended_text]
    return " ".join(value for value in values if value).lower()


def _entry_vector_json(entry: KnowledgeIndexEntry) -> str:
    return json.dumps(embed_text(_entry_search_text(entry)), separators=(",", ":"))


def sync_sqlite_knowledge_index(entries: Iterable[KnowledgeIndexEntry], *, root: Path) -> dict[str, Any]:
    """Replace the SQLite sidecar with the supplied index entries."""

    entry_list = list(entries)
    path = sqlite_knowledge_index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _connect(path) as connection:
        _ensure_schema(connection)
        connection.execute("DELETE FROM index_entries")
        connection.execute("DELETE FROM index_entries_fts")
        for entry in entry_list:
            payload = _entry_payload(entry)
            columns = _entry_search_columns(entry)
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
                    semantic_vector
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _entry_search_text(entry),
                    _entry_vector_json(entry),
                ),
            )
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
                    project_types
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
        connection.commit()

    return {
        "path": str(path),
        "entries": len(entry_list),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


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


def _rows_to_entries(rows: Iterable[sqlite3.Row]) -> list[KnowledgeIndexEntry]:
    entries: list[KnowledgeIndexEntry] = []
    seen: set[str] = set()
    for row in rows:
        index_id = str(row["index_id"])
        if index_id in seen:
            continue
        seen.add(index_id)
        entries.append(KnowledgeIndexEntry(**json.loads(row["entry_json"])))
    return entries


def _fetch_fts_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexEntry]:
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
        SELECT e.index_id, e.entry_json
        FROM index_entries e
        JOIN index_entries_fts ON e.index_id = index_entries_fts.index_id
        {where_sql}
        ORDER BY bm25(index_entries_fts, {weights}), e.confidence DESC, e.updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return _rows_to_entries(rows)


def _fetch_like_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexEntry]:
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
        SELECT e.index_id, e.entry_json
        FROM index_entries e
        {where_sql}
        ORDER BY e.confidence DESC, e.updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return _rows_to_entries(rows)


def _fetch_semantic_entries(
    connection: sqlite3.Connection,
    request: KnowledgeIndexSearchRequest,
    *,
    limit: int,
) -> list[KnowledgeIndexEntry]:
    if not request.query.strip():
        return []

    query_vector = embed_text(request.query)
    clauses, params = _base_filters(request)
    where_sql = _where_sql(clauses)
    rows = connection.execute(
        f"""
        SELECT e.index_id, e.entry_json, e.semantic_vector
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
        if similarity <= 0.08:
            continue
        scored.append((similarity, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return _rows_to_entries(row for _, row in scored[:limit])


def search_sqlite_knowledge_index_candidates(
    request: KnowledgeIndexSearchRequest,
    *,
    root: Path,
) -> list[KnowledgeIndexEntry] | None:
    """Return SQLite-backed candidates, or None when the sidecar is unavailable."""

    path = sqlite_knowledge_index_path(root)
    if not path.exists():
        return None

    limit = _candidate_limit(request.limit)
    with _connect(path) as connection:
        _ensure_schema(connection)
        if not request.query.strip():
            return _fetch_like_entries(connection, request, limit=limit)

        entries: list[KnowledgeIndexEntry] = []
        seen: set[str] = set()
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
        for entry in ordered_sources:
            if entry.index_id in seen:
                continue
            seen.add(entry.index_id)
            entries.append(entry)
        return entries
