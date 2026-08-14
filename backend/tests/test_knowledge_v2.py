from __future__ import annotations

import os
from pathlib import Path

import pytest

from deerflow.knowledge import (
    KnowledgeIndexBuildRequest,
    KnowledgeIndexSearchRequest,
    build_knowledge_index_from_folder,
    search_knowledge_index_entries,
)
from deerflow.knowledge import generator as knowledge_generator
from deerflow.knowledge import storage as knowledge_storage


@pytest.fixture(autouse=True)
def isolated_knowledge_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "knowledge_base"
    monkeypatch.setattr(knowledge_storage, "_knowledge_file_path", lambda *, user_id=None: root / "index.json")
    monkeypatch.setattr(knowledge_storage, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_generator, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_storage, "_storage_instance", knowledge_storage.FileKnowledgeBaseStorage())
    yield root
    monkeypatch.setattr(knowledge_storage, "_storage_instance", None)


def test_unclassified_plain_text_is_chunked_and_searchable(isolated_knowledge_storage: Path) -> None:
    source = isolated_knowledge_storage / "通用资料" / "其他" / "设备说明.txt"
    source.parent.mkdir(parents=True)
    source.write_text(
        "这是一份没有 Markdown 标题、没有申报章节标签的设备说明。\n\n设备支持 QX-9173 协议，并可在离线环境完成批量数据校验。\n\n这些内容仍然必须进入知识库全文索引。",
        encoding="utf-8",
    )

    build = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="通用资料"),
        user_id="alice",
    )
    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(query="QX-9173 离线批量数据校验", search_mode="keyword"),
        user_id="alice",
    )

    assert build.document_entries == 1
    assert build.section_entries >= 1
    assert response.count >= 1
    assert response.results[0].entry.entry_type in {"section", "subsection"}
    assert "content" in response.results[0].matched_fields

    incremental = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="通用资料"),
        user_id="alice",
    )
    assert incremental.scale_stats["embedding_generated_count"] == 0
    assert incremental.scale_stats["embedding_reused_count"] >= 2
    assert incremental.scale_stats["embedding_fallback"] is False


def test_full_chunk_body_is_indexed_beyond_short_summary(isolated_knowledge_storage: Path) -> None:
    source = isolated_knowledge_storage / "技术资料" / "通用" / "接口规范.md"
    source.parent.mkdir(parents=True)
    prefix = "接口背景和通用说明。" * 40
    source.write_text(
        f"# 接口规范\n\n## 数据交换约束\n\n{prefix}\n\n最终兼容格式包括 AXF、B17X 和 QDATA-9，校验码采用双阶段回退机制。",
        encoding="utf-8",
    )

    build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="技术资料"),
        user_id="alice",
    )
    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(query="QDATA-9 双阶段回退机制", search_mode="keyword"),
        user_id="alice",
    )

    assert response.count >= 1
    assert response.results[0].entry.source_file_path == "技术资料/通用/接口规范.md"
    assert "content" in response.results[0].matched_fields


def test_chunk_assets_use_canonical_knowledge_uri(isolated_knowledge_storage: Path) -> None:
    from deerflow.knowledge.content_store import resolve_knowledge_file_uri

    source = isolated_knowledge_storage / "技术资料" / "通用" / "图文报告.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fixture")
    asset = source.with_name(f"{source.name}.assets") / "images" / "figure.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"image")
    cache = source.with_suffix(".pdf.mineru.md")
    cache.write_text(
        "# 图文报告\n\n## 系统结构\n\n系统采用分层结构。\n\n![系统结构图](图文报告.pdf.assets/images/figure.png)",
        encoding="utf-8",
    )
    os.utime(cache, (source.stat().st_mtime + 1, source.stat().st_mtime + 1))

    result = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="技术资料"),
        user_id="alice",
    )
    chunk_text = next(text for entry in result.entries if entry.entry_type in {"section", "subsection"} for text in [(isolated_knowledge_storage / entry.file_path).read_text(encoding="utf-8")] if "knowledge-file://" in text)
    uri = next(part.split(")", 1)[0] for part in chunk_text.split("(")[1:] if part.startswith("knowledge-file://"))

    assert "knowledge-file://" in chunk_text
    assert resolve_knowledge_file_uri(uri, root=isolated_knowledge_storage) == asset.resolve()


def test_short_sibling_blocks_are_merged_without_losing_source_anchors(isolated_knowledge_storage: Path) -> None:
    source = isolated_knowledge_storage / "技术资料" / "通用" / "短章节.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 短章节集合\n\n## 设备准备\n\n准备采集设备和校准工具。\n\n## 环境检查\n\n检查温度、湿度和供电状态。\n\n## 数据采集\n\n按照规定频率执行数据采集。",
        encoding="utf-8",
    )

    result = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="技术资料"),
        user_id="alice",
    )
    chunks = [entry for entry in result.entries if entry.entry_type in {"section", "subsection"}]

    assert len(chunks) < 3
    assert any(len(entry.metadata.get("source_anchors", [])) >= 2 for entry in chunks)
    combined = "\n".join((isolated_knowledge_storage / entry.file_path).read_text(encoding="utf-8") for entry in chunks)
    assert "准备采集设备" in combined
    assert "检查温度" in combined
    assert "规定频率" in combined


def test_split_chunks_form_an_ordered_context_group(isolated_knowledge_storage: Path) -> None:
    source = isolated_knowledge_storage / "技术资料" / "通用" / "研究现状.md"
    source.parent.mkdir(parents=True)
    paragraphs = [f"第{index}部分研究现状。" + (f"特征{index}的对比分析。" * 150) for index in range(1, 4)]
    source.write_text("# 专题报告\n\n## 国内外研究现状\n\n" + "\n\n".join(paragraphs), encoding="utf-8")

    result = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="技术资料"),
        user_id="alice",
    )
    chunks = [entry for entry in result.entries if entry.metadata.get("chunk_group_id") and entry.source_anchor == "国内外研究现状"]

    assert len(chunks) == 3
    chunks.sort(key=lambda entry: entry.metadata["chunk_sequence"])
    assert {entry.metadata["chunk_group_id"] for entry in chunks} == {chunks[0].metadata["chunk_group_id"]}
    assert [entry.metadata["chunk_sequence"] for entry in chunks] == [1, 2, 3]
    assert all(entry.metadata["chunk_count"] == 3 for entry in chunks)
    assert chunks[0].metadata["previous_chunk_id"] is None
    assert chunks[0].metadata["next_chunk_id"] == chunks[1].metadata["chunk_id"]
    assert chunks[1].metadata["previous_chunk_id"] == chunks[0].metadata["chunk_id"]
    assert chunks[1].metadata["next_chunk_id"] == chunks[2].metadata["chunk_id"]
    assert chunks[2].metadata["previous_chunk_id"] == chunks[1].metadata["chunk_id"]
    assert chunks[2].metadata["next_chunk_id"] is None

    group_id = chunks[0].metadata["chunk_group_id"]
    grouped = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query=group_id,
            metadata_filters={"chunk_group_id": group_id},
            search_mode="keyword",
        ),
        user_id="alice",
    )
    assert [result.entry.metadata["chunk_sequence"] for result in grouped.results] == [1, 2, 3]


def test_configured_embedding_provider_is_batched_and_used_for_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    from deerflow.knowledge import embeddings

    class StubConfig:
        enabled = True
        use = "test:StubEmbeddings"
        batch_size = 2

        @staticmethod
        def provider_kwargs() -> dict[str, str]:
            return {"model": "stub-embedding-v1"}

    class StubProvider:
        document_batches: list[list[str]] = []

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.document_batches.append(texts)
            return [[float(len(text)), 1.0] for text in texts]

        def embed_query(self, text: str) -> list[float]:
            return [float(len(text)), 2.0]

    provider = StubProvider()
    monkeypatch.setattr(embeddings, "_embedding_config", lambda: StubConfig())
    monkeypatch.setattr(embeddings, "_provider", lambda: provider)

    vectors, signature = embeddings.embed_documents_with_signature(["a", "bb", "ccc"])
    query_vector = embeddings.embed_query_for_signature("query", signature)

    assert provider.document_batches == [["a", "bb"], ["ccc"]]
    assert vectors == [[1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]
    assert query_vector == [5.0, 2.0]
    assert signature.startswith("test:StubEmbeddings:")


def _index_entry(index_id: str, file_path: str, *, summary: str = ""):
    from deerflow.knowledge.schemas import KnowledgeIndexEntry

    return KnowledgeIndexEntry(
        index_id=index_id,
        title=Path(file_path).stem,
        entry_type="section",
        category="通用资料",
        file_path=file_path,
        summary=summary,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def test_sqlite_reuses_unchanged_embeddings_and_rebuilds_after_model_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.knowledge import sqlite_index

    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "chunk.md").write_text("稳定的正文内容。", encoding="utf-8")
    entry = _index_entry("idx_stable", "chunk.md")
    signature = ["remote-embedding:v1"]
    calls: list[list[str]] = []

    monkeypatch.setattr(sqlite_index, "configured_embedding_signature", lambda: signature[0])

    def embed(texts: list[str]):
        calls.append(texts)
        return [[float(len(text)), 1.0] for text in texts], signature[0]

    monkeypatch.setattr(sqlite_index, "embed_documents_with_signature", embed)

    first = sqlite_index.sync_sqlite_knowledge_index([entry], root=root)
    second = sqlite_index.sync_sqlite_knowledge_index([entry], root=root)
    metadata_only_change = entry.model_copy(update={"updated_at": "2026-01-02T00:00:00+00:00"})
    third = sqlite_index.sync_sqlite_knowledge_index([metadata_only_change], root=root)
    signature[0] = "remote-embedding:v2"
    switched = sqlite_index.sync_sqlite_knowledge_index([metadata_only_change], root=root)

    assert first["embedding_generated_count"] == 1
    assert second["embedding_reused_count"] == 1
    assert third["embedding_reused_count"] == 1
    assert switched["embedding_reused_count"] == 0
    assert switched["embedding_generated_count"] == 1
    assert len(calls) == 2


def test_embedding_failure_rebuilds_all_vectors_in_one_local_space(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.knowledge import sqlite_index

    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "first.md").write_text("第一块正文。", encoding="utf-8")
    (root / "second.md").write_text("第二块正文。", encoding="utf-8")
    entries = [_index_entry("idx_first", "first.md"), _index_entry("idx_second", "second.md")]
    provider_fails = [False]
    local_batches: list[list[str]] = []

    monkeypatch.setattr(sqlite_index, "configured_embedding_signature", lambda: "remote-embedding:v1")

    def embed(texts: list[str]):
        signature = sqlite_index.LOCAL_HASH_SIGNATURE if provider_fails[0] else "remote-embedding:v1"
        return [[float(len(text)), 1.0] for text in texts], signature

    def embed_locally(texts: list[str]):
        local_batches.append(texts)
        return [[float(len(text)), 0.0] for text in texts]

    monkeypatch.setattr(sqlite_index, "embed_documents_with_signature", embed)
    monkeypatch.setattr(sqlite_index, "embed_texts_locally", embed_locally)
    sqlite_index.sync_sqlite_knowledge_index(entries, root=root)

    provider_fails[0] = True
    changed = [entries[0], entries[1].model_copy(update={"summary": "摘要已变更"})]
    result = sqlite_index.sync_sqlite_knowledge_index(changed, root=root)
    persisted = sqlite_index.sqlite_knowledge_index_stats(root)

    assert result["embedding_fallback"] is True
    assert result["embedding_reused_count"] == 0
    assert result["embedding_generated_count"] == 2
    assert len(local_batches) == 1
    assert len(local_batches[0]) == 2
    assert persisted["embedding_signature"] == sqlite_index.LOCAL_HASH_SIGNATURE
    assert persisted["embedding_fallback"] is True
