"""Format-neutral post-build quality checks for the knowledge index."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

from deerflow.config import get_app_config
from deerflow.knowledge.content_store import load_index_entry_content, resolve_knowledge_file_uri
from deerflow.knowledge.schemas import (
    KnowledgeBuildQualityIssue,
    KnowledgeBuildQualityReport,
    KnowledgeIndexEntry,
)
from deerflow.knowledge.sqlite_index import sqlite_knowledge_content_map

_KNOWLEDGE_URI_RE = re.compile(r"knowledge-file://[^\s)>\"]+")
_LOCAL_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?!https?://|data:|knowledge-file://)([^\s)]+)")


def evaluate_knowledge_build_quality(
    entries: list[KnowledgeIndexEntry],
    *,
    root: Path,
) -> KnowledgeBuildQualityReport:
    """Evaluate searchable bodies, chunk graph integrity, and asset references."""

    config = get_app_config().knowledge_retrieval.quality
    if not config.enabled:
        return KnowledgeBuildQualityReport(enabled=False, passed=True, score=100.0)

    issues: list[KnowledgeBuildQualityIssue] = []
    error_count = 0
    warning_count = 0

    def add_issue(
        code: str,
        severity: str,
        message: str,
        *,
        entry: KnowledgeIndexEntry | None = None,
        chunk_group_id: str | None = None,
    ) -> None:
        nonlocal error_count, warning_count
        if severity == "error":
            error_count += 1
        else:
            warning_count += 1
        if len(issues) >= config.max_reported_issues:
            return
        issues.append(
            KnowledgeBuildQualityIssue(
                code=code,
                severity=severity,
                message=message,
                file_path=entry.file_path if entry else None,
                index_id=entry.index_id if entry else None,
                chunk_group_id=chunk_group_id,
            )
        )

    text_entries = [entry for entry in entries if entry.entry_type in {"document", "section", "subsection"}]
    document_entries = [entry for entry in text_entries if entry.entry_type == "document"]
    chunk_entries = [entry for entry in text_entries if entry.entry_type in {"section", "subsection"}]
    bodies: dict[str, str] = {}
    empty_documents = 0
    empty_chunks = 0
    short_chunks = 0
    oversized_chunks = 0
    broken_assets = 0
    duplicate_chunk_file_paths = 0

    chunk_paths: dict[str, list[KnowledgeIndexEntry]] = defaultdict(list)
    for entry in chunk_entries:
        chunk_paths[entry.file_path].append(entry)
    for file_path, path_entries in chunk_paths.items():
        if len(path_entries) < 2:
            continue
        duplicate_chunk_file_paths += len(path_entries) - 1
        for entry in path_entries[1:]:
            add_issue(
                "duplicate_chunk_file_path",
                "error",
                f"多个分块指向同一个文件，后写入的正文可能已覆盖前一分块：{file_path}",
                entry=entry,
            )

    duplicate_bodies: dict[str, list[KnowledgeIndexEntry]] = defaultdict(list)
    indexed_bodies = sqlite_knowledge_content_map(root)
    for entry in text_entries:
        body = indexed_bodies.get(entry.index_id)
        if body is None:
            body = load_index_entry_content(root, entry, max_chars=1_000_000)
        bodies[entry.index_id] = body
        if not body.strip():
            if entry.entry_type == "document":
                empty_documents += 1
            else:
                empty_chunks += 1
            add_issue("empty_searchable_body", "error", "索引条目没有可检索正文。", entry=entry)
            continue

        normalized = " ".join(body.split())
        if entry.entry_type in {"section", "subsection"}:
            duplicate_bodies[hashlib.sha256(normalized.encode("utf-8")).hexdigest()].append(entry)
            chunk_kind = str(entry.metadata.get("chunk_kind") or "")
            if chunk_kind == "leaf_evidence" and len(normalized) < config.minimum_leaf_chunk_chars:
                short_chunks += 1
                add_issue(
                    "short_leaf_chunk",
                    "warning",
                    f"叶子分块正文仅 {len(normalized)} 字，可能缺少独立检索价值。",
                    entry=entry,
                )
            if len(normalized) > config.maximum_chunk_chars:
                oversized_chunks += 1
                add_issue(
                    "oversized_chunk",
                    "warning",
                    f"分块正文共 {len(normalized)} 字，超过 {config.maximum_chunk_chars} 字阈值。",
                    entry=entry,
                )

        for uri in _KNOWLEDGE_URI_RE.findall(body):
            try:
                resolve_knowledge_file_uri(uri, root=root)
            except (ValueError, FileNotFoundError):
                broken_assets += 1
                add_issue("broken_asset_uri", "error", f"资源引用无法解析：{uri}", entry=entry)

        source_path = entry.source_file_path or entry.file_path
        source_parent = (root / source_path).resolve().parent
        for raw_target in _LOCAL_IMAGE_RE.findall(body):
            target = unquote(raw_target.split("#", 1)[0].split("?", 1)[0])
            resolved = (source_parent / target).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                exists = False
            else:
                exists = resolved.is_file()
            if not exists:
                broken_assets += 1
                add_issue("broken_local_asset", "error", f"本地图片引用不存在：{raw_target}", entry=entry)

    duplicate_chunk_bodies = 0
    for duplicate_entries in duplicate_bodies.values():
        if len(duplicate_entries) < 2:
            continue
        duplicate_chunk_bodies += len(duplicate_entries) - 1
        for entry in duplicate_entries[1:]:
            add_issue("duplicate_chunk_body", "warning", "该分块正文与另一个分块完全重复。", entry=entry)

    llm_chunked_chunks = sum(1 for entry in chunk_entries if entry.metadata.get("chunking_strategy") == "llm_semantic")

    groups: dict[str, list[KnowledgeIndexEntry]] = defaultdict(list)
    for entry in chunk_entries:
        group_id = str(entry.metadata.get("chunk_group_id") or "")
        if group_id:
            groups[group_id].append(entry)

    invalid_chunk_groups = 0
    for group_id, members in groups.items():
        members.sort(key=lambda item: int(item.metadata.get("chunk_sequence", 0)))
        declared_counts = {int(item.metadata.get("chunk_count", 0)) for item in members}
        sequences = [int(item.metadata.get("chunk_sequence", 0)) for item in members]
        valid = declared_counts == {len(members)} and sequences == list(range(1, len(members) + 1))
        chunk_ids = [str(item.metadata.get("chunk_id") or "") for item in members]
        if any(not chunk_id for chunk_id in chunk_ids) or len(set(chunk_ids)) != len(chunk_ids):
            valid = False
        for index, member in enumerate(members):
            expected_previous = chunk_ids[index - 1] if index > 0 else None
            expected_next = chunk_ids[index + 1] if index + 1 < len(chunk_ids) else None
            if member.metadata.get("previous_chunk_id") != expected_previous:
                valid = False
            if member.metadata.get("next_chunk_id") != expected_next:
                valid = False
        if not valid:
            invalid_chunk_groups += 1
            add_issue(
                "invalid_chunk_group",
                "error",
                "分块组的数量、顺序或前后链接不完整。",
                entry=members[0],
                chunk_group_id=group_id,
            )

    source_chunks: dict[str, list[KnowledgeIndexEntry]] = defaultdict(list)
    for entry in chunk_entries:
        if entry.metadata.get("chunk_id"):
            source_chunks[entry.source_file_path or entry.file_path].append(entry)

    invalid_document_chunk_links = 0
    for source_path, members in source_chunks.items():
        members.sort(key=lambda item: int(item.metadata.get("chunk_order", 0)))
        chunk_ids = [str(item.metadata.get("chunk_id") or "") for item in members]
        valid = len(set(chunk_ids)) == len(chunk_ids) and all(chunk_ids)
        for index, member in enumerate(members):
            expected_previous = chunk_ids[index - 1] if index > 0 else None
            expected_next = chunk_ids[index + 1] if index + 1 < len(chunk_ids) else None
            if member.metadata.get("document_previous_chunk_id") != expected_previous:
                valid = False
            if member.metadata.get("document_next_chunk_id") != expected_next:
                valid = False
        if not valid:
            invalid_document_chunk_links += 1
            add_issue(
                "invalid_document_chunk_links",
                "error",
                f"同一来源文档内的分块顺序链接不完整：{source_path}",
                entry=members[0],
            )

    nonempty_documents = len(document_entries) - empty_documents
    nonempty_chunks = len(chunk_entries) - empty_chunks
    document_coverage = nonempty_documents / len(document_entries) if document_entries else 1.0
    chunk_coverage = nonempty_chunks / len(chunk_entries) if chunk_entries else 1.0
    body_coverage = (nonempty_documents + nonempty_chunks) / len(text_entries) if text_entries else 1.0
    if body_coverage < config.minimum_body_coverage:
        add_issue(
            "body_coverage_below_threshold",
            "error",
            f"可检索正文覆盖率为 {body_coverage:.1%}，低于 {config.minimum_body_coverage:.1%} 门槛。",
        )

    score = max(0.0, 100.0 - error_count * 10.0 - warning_count * 2.0)
    return KnowledgeBuildQualityReport(
        enabled=True,
        passed=error_count == 0 and body_coverage >= config.minimum_body_coverage,
        score=score,
        checked_entries=len(text_entries),
        error_count=error_count,
        warning_count=warning_count,
        metrics={
            "body_coverage": round(body_coverage, 4),
            "document_body_coverage": round(document_coverage, 4),
            "chunk_body_coverage": round(chunk_coverage, 4),
            "empty_documents": empty_documents,
            "empty_chunks": empty_chunks,
            "short_chunks": short_chunks,
            "oversized_chunks": oversized_chunks,
            "duplicate_chunk_bodies": duplicate_chunk_bodies,
            "llm_chunked_chunks": llm_chunked_chunks,
            "duplicate_chunk_file_paths": duplicate_chunk_file_paths,
            "chunk_groups": len(groups),
            "invalid_chunk_groups": invalid_chunk_groups,
            "invalid_document_chunk_links": invalid_document_chunk_links,
            "broken_asset_references": broken_assets,
            "issues_truncated": error_count + warning_count > len(issues),
        },
        issues=issues,
    )
