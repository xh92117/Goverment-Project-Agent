import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import knowledge, proposal_drafts
from deerflow.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeFileReadRequest,
    KnowledgeFileSaveRequest,
    KnowledgeIndexBuildRequest,
    KnowledgeIndexEntryCreate,
    KnowledgeIndexListRequest,
    KnowledgeIndexSearchRequest,
    KnowledgeOrganizeOptions,
    KnowledgeRecallEvalCase,
    KnowledgeRecallEvalRequest,
    KnowledgeSearchRequest,
    build_knowledge_index_from_folder,
    create_knowledge_document,
    create_knowledge_index_entry,
    evaluate_knowledge_recall,
    list_knowledge_index_entries_page,
    organize_incoming_files,
    read_knowledge_file,
    save_knowledge_file,
    search_knowledge_documents,
    search_knowledge_index_entries,
)
from deerflow.knowledge import extractors as knowledge_extractors
from deerflow.knowledge import generator as knowledge_generator
from deerflow.knowledge import organizer as knowledge_organizer
from deerflow.knowledge import storage as knowledge_storage
from deerflow.tools.builtins.knowledge_tools import (
    knowledge_incremental_update_tool,
    knowledge_read_file_tool,
    knowledge_search_index_tool,
)
from deerflow.tools.builtins.proposal_workspace_tool import proposal_save_markdown_tool
from deerflow.tools.tools import get_available_tools


def _write_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    body = "".join(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    document_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
    path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)


@pytest.fixture(autouse=True)
def isolated_knowledge_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Use a per-test JSON file so knowledge-base tests do not touch real data."""

    monkeypatch.setattr(
        knowledge_storage,
        "_knowledge_file_path",
        lambda *, user_id=None: tmp_path / "knowledge_base" / "index.json",
    )
    monkeypatch.setattr(
        knowledge_storage,
        "_knowledge_root_path",
        lambda *, user_id=None: tmp_path / "knowledge_base",
    )
    monkeypatch.setattr(
        knowledge_generator,
        "_knowledge_root_path",
        lambda *, user_id=None: tmp_path / "knowledge_base",
    )
    monkeypatch.setattr(
        knowledge_organizer,
        "_knowledge_root_path",
        lambda *, user_id=None: tmp_path / "knowledge_base",
    )
    monkeypatch.setattr(knowledge_storage, "_storage_instance", knowledge_storage.FileKnowledgeBaseStorage())
    yield
    monkeypatch.setattr(knowledge_storage, "_storage_instance", None)


def _create_doc(
    *,
    title: str,
    library: str = "research_foundations",
    doc_type: str = "research_foundation",
    content: str = "",
    metadata: dict | None = None,
    confidentiality_level: str = "internal",
):
    return create_knowledge_document(
        KnowledgeDocumentCreate(
            title=title,
            library=library,
            doc_type=doc_type,
            content=content,
            metadata=metadata or {},
            confidentiality_level=confidentiality_level,
        ),
        user_id="alice",
    )


def test_search_matches_content_and_metadata_filters() -> None:
    _create_doc(
        title="智能制造前期研究基础",
        content="团队已完成工业视觉检测算法和示范产线验证。",
        metadata={"domain": "智能制造", "project_type": "重点研发"},
    )
    _create_doc(
        title="生物医药团队成果",
        library="team_achievements",
        doc_type="award",
        content="团队获得生物医药相关奖励。",
        metadata={"domain": "生物医药"},
    )

    response = search_knowledge_documents(
        KnowledgeSearchRequest(
            query="视觉检测",
            metadata_filters={"domain": "智能制造"},
        ),
        user_id="alice",
    )

    assert response.count == 1
    assert response.results[0].document.title == "智能制造前期研究基础"
    assert "content" in response.results[0].matched_fields


def test_search_excludes_restricted_documents_by_default() -> None:
    _create_doc(
        title="涉密历史申报书",
        library="historical_proposals",
        doc_type="historical_proposal",
        content="关键技术路线",
        confidentiality_level="restricted",
    )

    hidden = search_knowledge_documents(KnowledgeSearchRequest(query="关键技术"), user_id="alice")
    visible = search_knowledge_documents(
        KnowledgeSearchRequest(query="关键技术", include_restricted=True),
        user_id="alice",
    )

    assert hidden.count == 0
    assert visible.count == 1


def test_knowledge_router_create_list_search_and_get() -> None:
    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/knowledge/documents",
            json={
                "title": "省级重点研发申报模板",
                "library": "application_templates",
                "doc_type": "application_template",
                "content": "章节包括研究基础、技术路线和预算说明。",
                "metadata": {"project_level": "省级", "project_type": "重点研发"},
                "confidentiality_level": "internal",
            },
        )
        assert create_response.status_code == 200
        document = create_response.json()

        list_response = client.get("/api/knowledge/documents?library=application_templates")
        assert list_response.status_code == 200
        assert [item["document_id"] for item in list_response.json()] == [document["document_id"]]

        search_response = client.post(
            "/api/knowledge/search",
            json={
                "query": "技术路线",
                "libraries": ["application_templates"],
                "metadata_filters": {"project_level": "省级"},
            },
        )
        assert search_response.status_code == 200
        assert search_response.json()["count"] == 1

        get_response = client.get(f"/api/knowledge/documents/{document['document_id']}")
        assert get_response.status_code == 200
        assert get_response.json()["title"] == "省级重点研发申报模板"


def test_knowledge_router_returns_404_for_missing_document() -> None:
    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        response = client.get("/api/knowledge/documents/kb_missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Knowledge document 'kb_missing' not found."


def test_index_search_points_to_source_file_and_section(tmp_path: Path) -> None:
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="工业视觉检测国内外研究现状",
            category="国内外研究现状",
            domain="智能制造",
            keywords=["工业视觉", "缺陷检测"],
            summary="适合支撑工业视觉检测方向的国内外研究现状写作。",
            file_path="国内外研究现状/人工智能/工业视觉检测研究现状.md",
            recommended_sections=[
                {
                    "heading": "国内研究现状",
                    "anchor": "国内研究现状",
                    "use_for": ["国内外研究现状"],
                }
            ],
            applicable_chapters=["国内外研究现状"],
            project_types=["重点研发"],
        ),
        user_id="alice",
    )

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="工业视觉 缺陷检测",
            categories=["国内外研究现状"],
            applicable_chapters=["国内外研究现状"],
        ),
        user_id="alice",
    )

    assert response.count == 1
    entry = response.results[0].entry
    assert entry.file_path == "国内外研究现状/人工智能/工业视觉检测研究现状.md"
    assert entry.recommended_sections[0].anchor == "国内研究现状"


def test_read_knowledge_file_extracts_markdown_heading(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "国内外研究现状" / "人工智能" / "工业视觉检测研究现状.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 工业视觉检测研究现状\n\n总述。\n\n## 国外研究现状\n\n国外内容。\n\n## 国内研究现状\n\n国内工业视觉检测研究正在快速发展。\n\n### 代表性方法\n\n深度学习方法应用广泛。\n\n## 现有问题\n\n问题内容。\n",
        encoding="utf-8",
    )

    response = read_knowledge_file(
        KnowledgeFileReadRequest(
            file_path="国内外研究现状/人工智能/工业视觉检测研究现状.md",
            anchor="国内研究现状",
        ),
        user_id="alice",
    )

    assert "## 国内研究现状" in response.content
    assert "深度学习方法应用广泛" in response.content
    assert "## 现有问题" not in response.content


def test_read_knowledge_file_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="path traversal"):
        read_knowledge_file(
            KnowledgeFileReadRequest(file_path="../secret.md"),
            user_id="alice",
        )


def test_save_knowledge_file_replaces_markdown_heading(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "国内外研究现状" / "人工智能" / "工业视觉检测研究现状.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 工业视觉检测研究现状\n\n总述。\n\n## 国内研究现状\n\n旧内容。\n\n## 现有问题\n\n问题内容。\n",
        encoding="utf-8",
    )

    response = save_knowledge_file(
        KnowledgeFileSaveRequest(
            file_path="国内外研究现状/人工智能/工业视觉检测研究现状.md",
            anchor="国内研究现状",
            content="## 国内研究现状\n\n修订后的研究现状。",
        ),
        user_id="alice",
    )

    saved = source.read_text(encoding="utf-8")
    assert response.saved is True
    assert response.bytes_written == len(saved.encode("utf-8"))
    assert "修订后的研究现状" in saved
    assert "旧内容" not in saved
    assert "## 现有问题\n\n问题内容。" in saved


def test_save_knowledge_file_rejects_unsupported_extension(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "政策指南" / "省级重点研发指南.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")

    with pytest.raises(ValueError, match="markdown and plain-text"):
        save_knowledge_file(
            KnowledgeFileSaveRequest(
                file_path="政策指南/省级重点研发指南.pdf",
                content="# 修订内容",
            ),
            user_id="alice",
        )


def test_knowledge_router_index_search_and_file_read(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "国内外研究现状" / "人工智能" / "工业视觉检测研究现状.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 标题\n\n## 国内研究现状\n\n索引命中的原始资料。\n", encoding="utf-8")

    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/knowledge/index",
            json={
                "title": "工业视觉检测国内外研究现状",
                "category": "国内外研究现状",
                "domain": "智能制造",
                "keywords": ["工业视觉"],
                "summary": "适合国内外研究现状章节。",
                "file_path": "国内外研究现状/人工智能/工业视觉检测研究现状.md",
                "recommended_sections": [
                    {
                        "heading": "国内研究现状",
                        "anchor": "国内研究现状",
                        "use_for": ["国内外研究现状"],
                    }
                ],
                "applicable_chapters": ["国内外研究现状"],
                "project_types": ["重点研发"],
            },
        )
        assert create_response.status_code == 200

        search_response = client.post(
            "/api/knowledge/index/search",
            json={
                "query": "工业视觉",
                "categories": ["国内外研究现状"],
                "applicable_chapters": ["国内外研究现状"],
            },
        )
        assert search_response.status_code == 200
        assert search_response.json()["count"] == 1

        read_response = client.post(
            "/api/knowledge/files/read",
            json={
                "file_path": "国内外研究现状/人工智能/工业视觉检测研究现状.md",
                "anchor": "国内研究现状",
            },
        )
        assert read_response.status_code == 200
        assert read_response.json()["content"] == "## 国内研究现状\n\n索引命中的原始资料。"

        save_response = client.put(
            "/api/knowledge/files/save",
            json={
                "file_path": "国内外研究现状/人工智能/工业视觉检测研究现状.md",
                "anchor": "国内研究现状",
                "content": "## 国内研究现状\n\n已修改的原始资料。",
            },
        )
        assert save_response.status_code == 200
        assert save_response.json()["saved"] is True
        assert source.read_text(encoding="utf-8") == "# 标题\n\n## 国内研究现状\n\n已修改的原始资料。\n"


def test_build_knowledge_index_from_folder_creates_entries(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "国内外研究现状" / "人工智能" / "工业视觉检测研究现状.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 工业视觉检测研究现状\n\n该资料适合工业视觉检测方向申报书写作。\n\n## 国外研究现状\n\n国外研究内容。\n\n## 国内研究现状\n\n国内研究内容。\n\n## 现有问题\n\n现有问题内容。\n",
        encoding="utf-8",
    )

    response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="国内外研究现状"),
        user_id="alice",
    )

    assert response.scanned_files == 1
    assert response.document_entries == 1
    assert response.section_entries >= 2
    entry = response.entries[0]
    assert entry.title == "工业视觉检测研究现状"
    assert entry.category == "国内外研究现状"
    assert entry.domain == "人工智能"
    assert entry.file_path == "国内外研究现状/人工智能/工业视觉检测研究现状.md"
    assert "国内外研究现状" in entry.proposal_sections
    section_entry = next(item for item in response.entries if item.entry_type in {"section", "subsection"} and "国内研究现状" in item.title)
    assert "国内外研究现状" in section_entry.proposal_sections
    assert section_entry.file_path.startswith("申报书章节分块/")
    assert (root / section_entry.file_path).exists()
    chunk_parts = Path(section_entry.file_path).parts
    assert chunk_parts[0] == "申报书章节分块"
    assert entry.title in chunk_parts
    assert Path(section_entry.file_path).name == "国内研究现状.md"
    assert (tmp_path / "knowledge_base" / "index.json").exists()
    assert source.exists()
    assert response.parser_counts["text:.md"] == 1
    assert response.parse_errors == []
    assert response.scale_stats["source_files_scanned"] == 1
    assert response.scale_stats["index_entries_total"] >= response.document_entries + response.section_entries
    assert response.scale_stats["index_json_bytes"] > 0
    assert response.scale_stats["sqlite_index_enabled"] is True
    assert response.scale_stats["sqlite_index_bytes"] > 0
    assert (root / ".index" / "knowledge.sqlite3").exists()


def test_build_index_reuses_unchanged_source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "历史申报书" / "路基工程" / "路基评估申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 路基评估申报书\n\n## 1.3 国内外研究现状\n\n路基检测现状。", encoding="utf-8")

    first = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="历史申报书"), user_id="alice")

    def fail_extract(path: Path):
        raise AssertionError(f"unchanged file should not be reparsed: {path}")

    monkeypatch.setattr(knowledge_generator, "extract_text_with_metadata", fail_extract)
    second = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="历史申报书"), user_id="alice")

    assert first.document_entries == 1
    assert second.created == 0
    assert second.updated == 0
    assert second.reused >= first.document_entries + first.section_entries
    assert second.parser_counts == {}


def test_build_index_supports_csv_table_files(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "预算依据" / "通用" / "预算测算表.csv"
    source.parent.mkdir(parents=True)
    source.write_text("预算科目,金额,说明\n设备费,100,检测设备\n测试化验加工费,20,现场试验\n", encoding="utf-8")

    response = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="预算依据"), user_id="alice")

    assert response.document_entries == 1
    assert response.parser_counts["table:csv"] == 1
    entry = response.entries[0]
    assert entry.file_path == "预算依据/通用/预算测算表.csv"
    assert entry.category == "预算依据"
    read_response = read_knowledge_file(KnowledgeFileReadRequest(file_path=entry.file_path), user_id="alice")
    assert "|预算科目|金额|说明|" in read_response.content


def test_build_index_supports_xlsx_table_files(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    root = tmp_path / "knowledge_base"
    source = root / "预算依据" / "通用" / "预算模板.xlsx"
    source.parent.mkdir(parents=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "经费预算"
    sheet.append(["预算科目", "金额"])
    sheet.append(["设备费", 100])
    workbook.save(source)

    response = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="预算依据"), user_id="alice")

    assert response.document_entries == 1
    assert response.parser_counts["table:xlsx"] == 1
    assert response.entries[0].file_path == "预算依据/通用/预算模板.xlsx"


def test_index_pagination_and_recall_evaluation(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="省级重点研发申报指南",
            category="政策指南",
            domain="通用",
            keywords=["申报条件", "材料要求"],
            summary="省级重点研发项目申报条件与材料要求。",
            file_path="政策指南/通用/省级重点研发申报指南.md",
        ),
        user_id="alice",
    )
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="预算编制说明",
            category="预算依据",
            domain="通用",
            keywords=["预算科目", "经费"],
            summary="项目经费预算编制要求。",
            file_path="预算依据/通用/预算编制说明.md",
        ),
        user_id="alice",
    )

    page = list_knowledge_index_entries_page(KnowledgeIndexListRequest(offset=1, limit=1), user_id="alice")
    evaluation = evaluate_knowledge_recall(
        KnowledgeRecallEvalRequest(
            cases=[
                KnowledgeRecallEvalCase(
                    query="申报条件和材料要求",
                    expected_file_paths=["政策指南/通用/省级重点研发申报指南.md"],
                ),
                KnowledgeRecallEvalCase(
                    query="预算科目经费说明",
                    expected_categories=["预算依据"],
                ),
            ],
            limit=5,
        ),
        user_id="alice",
    )

    assert page.total == 2
    assert len(page.entries) == 1
    assert evaluation.total_cases == 2
    assert evaluation.hit_count == 2
    assert evaluation.mrr > 0


def test_index_search_uses_sqlite_sidecar_when_json_missing(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)

    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="Bridge health monitoring research status",
            category="research_status",
            domain="bridge_engineering",
            keywords=["bridge", "vibration", "laser"],
            technical_terms=["laser Doppler vibrometry"],
            summary="Laser vibration monitoring supports bridge health assessment.",
            file_path="research/bridge-health-monitoring.md",
            applicable_chapters=["domestic_foreign_status"],
            project_types=["research_project"],
        ),
        user_id="alice",
    )

    sqlite_path = root / ".index" / "knowledge.sqlite3"
    assert sqlite_path.exists()
    (root / "index.json").unlink()

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="laser vibration bridge",
            categories=["research_status"],
            applicable_chapters=["domestic_foreign_status"],
            limit=5,
        ),
        user_id="alice",
    )

    assert response.count == 1
    assert response.results[0].entry.file_path == "research/bridge-health-monitoring.md"


def test_index_search_expands_declaration_intent_terms(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)

    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="桥梁健康监测研究现状",
            category="历史申报书",
            domain="桥梁工程",
            keywords=["桥梁", "健康监测"],
            summary="适合支撑国内外研究现状和文献综述章节。",
            file_path="历史申报书/桥梁工程/桥梁健康监测研究现状.md",
            proposal_sections=["domestic_foreign_status"],
            applicable_chapters=["domestic_foreign_status"],
            project_types=["科研项目申报"],
        ),
        user_id="alice",
    )
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="桥梁健康监测技术路线",
            category="历史申报书",
            domain="桥梁工程",
            keywords=["桥梁", "健康监测"],
            summary="适合支撑技术路线和实施路径章节。",
            file_path="历史申报书/桥梁工程/桥梁健康监测技术路线.md",
            proposal_sections=["technical_route"],
            applicable_chapters=["technical_route"],
            project_types=["科研项目申报"],
        ),
        user_id="alice",
    )

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="桥梁健康监测文献综述",
            categories=["历史申报书"],
            limit=2,
        ),
        user_id="alice",
    )

    assert response.count == 2
    assert response.results[0].entry.file_path == "历史申报书/桥梁工程/桥梁健康监测研究现状.md"
    assert "proposal_sections" in response.results[0].matched_fields


def test_index_search_supports_complementary_lexical_queries() -> None:
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="企业申请单位条件",
            category="政策指南",
            keywords=["申请单位条件", "注册企业"],
            summary="申报单位应满足规定的注册和经营条件。",
            file_path="政策指南/企业申请单位条件.md",
            document_type="application_guide",
            year=2026,
        ),
        user_id="alice",
    )

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="企业申报资格",
            query_variants=["申请单位条件", "企业申请条件"],
            search_mode="keyword",
            limit=5,
        ),
        user_id="alice",
    )

    assert response.count == 1
    assert response.results[0].entry.file_path == "政策指南/企业申请单位条件.md"
    assert "申请单位条件" in response.results[0].matched_queries


def test_index_search_applies_policy_metadata_and_validity_filters() -> None:
    for year, valid_to in ((2025, "2025-12-31"), (2026, "2026-12-31")):
        create_knowledge_index_entry(
            KnowledgeIndexEntryCreate(
                title=f"{year}年度重点研发计划申报指南",
                category="政策指南",
                keywords=["重点研发", "申报条件"],
                file_path=f"政策指南/{year}重点研发指南.md",
                authority="某省科学技术厅",
                document_type="application_guide",
                year=year,
                valid_from=f"{year}-01-01",
                valid_to=valid_to,
            ),
            user_id="alice",
        )
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="2026年度重点研发计划申报指南",
            category="政策指南",
            keywords=["重点研发", "申报条件"],
            file_path="政策指南/其他部门2026重点研发指南.md",
            authority="其他部门",
            document_type="application_guide",
            year=2026,
            valid_from="2026-01-01",
            valid_to="2026-12-31",
        ),
        user_id="alice",
    )

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="重点研发申报条件",
            authorities=["某省科学技术厅"],
            document_types=["application_guide"],
            years=[2026],
            valid_on="2026-07-14",
            search_mode="keyword",
            limit=5,
        ),
        user_id="alice",
    )

    assert [result.entry.file_path for result in response.results] == ["政策指南/2026重点研发指南.md"]


def test_index_builder_infers_policy_authority_document_type_and_year(tmp_path: Path) -> None:
    source = tmp_path / "knowledge_base" / "政策指南" / "重点研发" / "2026申报通知.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 某省科学技术厅关于组织申报2026年度重点研发计划的通知\n\n申报单位应符合指南要求。",
        encoding="utf-8",
    )

    response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="政策指南"),
        user_id="alice",
    )
    document = next(entry for entry in response.entries if entry.entry_type == "document")

    assert document.authority == "某省科学技术厅"
    assert document.document_type == "application_notice"
    assert document.year == 2026


def test_index_search_score_is_bounded_to_100(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)
    terms = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "theta", "lambda"]
    query = " ".join(terms)

    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title=query,
            category="历史申报书",
            domain=query,
            keywords=terms,
            technical_terms=terms,
            methods=terms,
            research_objects=terms,
            proposal_sections=terms,
            summary=query,
            file_path="历史申报书/高命中测试.md",
            source_file_path="历史申报书/高命中测试.md",
            source_anchor=query,
            project_types=terms,
        ),
        user_id="alice",
    )

    response = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query=query,
            categories=["历史申报书"],
            limit=1,
        ),
        user_id="alice",
    )

    assert response.count == 1
    assert response.results[0].score == 100.0


def test_organize_incoming_files_moves_new_files_by_rules(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "路基质量评估项目申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 路基质量评估项目申报书\n\n1.3 国内外研究现状\n\n正文。", encoding="utf-8")

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")

    target = root / "历史申报书" / "路基工程" / "路基质量评估项目申报书.md"
    assert report.scanned == 1
    assert report.moved == 1
    assert report.files[0].target_path == "历史申报书/路基工程/路基质量评估项目申报书.md"
    assert target.exists()
    assert not source.exists()


def test_organize_incoming_files_classifies_tunnel_detection_research_plan(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "引水隧洞衬砌爬壁检测机器人检测系统研究方案.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 引水隧洞衬砌爬壁检测机器人检测系统研究方案\n\n本项目研究内容包括冲击回波、地质雷达和多源检测信息融合。",
        encoding="utf-8",
    )

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")

    assert report.scanned == 1
    assert report.moved == 1
    assert report.files[0].category == "历史申报书"
    assert report.files[0].domain == "隧洞检测"
    assert report.files[0].target_path == "历史申报书/隧洞检测/引水隧洞衬砌爬壁检测机器人检测系统研究方案.md"


def test_organize_incoming_files_moves_pdf_mineru_cache_with_source(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "引水隧洞衬砌爬壁检测机器人检测系统研究方案.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")
    source_cache = source.with_suffix(".pdf.mineru.md")
    source_cache.write_text(
        "# 引水隧洞衬砌爬壁检测机器人检测系统研究方案\n\n本项目研究内容包括冲击回波、地质雷达和多源检测信息融合。",
        encoding="utf-8",
    )

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")

    target = root / "历史申报书" / "隧洞检测" / "引水隧洞衬砌爬壁检测机器人检测系统研究方案.pdf"
    assert report.files[0].target_path == "历史申报书/隧洞检测/引水隧洞衬砌爬壁检测机器人检测系统研究方案.pdf"
    assert target.exists()
    assert target.with_suffix(".pdf.mineru.md").exists()
    assert not source.exists()
    assert not source_cache.exists()


def test_organize_incoming_files_removes_orphan_mineru_cache(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    orphan_cache = root / "_incoming" / "已整理项目.pdf.mineru.md"
    orphan_cache.parent.mkdir(parents=True)
    orphan_cache.write_text("# 已整理项目", encoding="utf-8")

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")

    assert report.scanned == 1
    assert report.skipped == 1
    assert report.files[0].reason == "removed orphan cache"
    assert not orphan_cache.exists()


def test_organize_incoming_files_moves_pdf_extractor_metadata_with_source(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "project-plan.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")
    source_cache = source.with_name(f"{source.name}.mineru.md")
    source_cache.write_text("# project plan", encoding="utf-8")
    source_metadata = source.with_name(f"{source.name}.extractor.json")
    source_metadata.write_text('{"parser":"pdf:mineru"}', encoding="utf-8")

    report = organize_incoming_files(
        KnowledgeOrganizeOptions(
            default_category="history",
            default_domain="tunnel",
            category_rules=(),
            domain_rules=(),
        ),
        user_id="alice",
    )

    target = root / "history" / "tunnel" / "project-plan.pdf"
    assert report.moved == 1
    assert target.exists()
    assert target.with_name(f"{target.name}.mineru.md").exists()
    assert target.with_name(f"{target.name}.extractor.json").exists()
    assert not source.exists()
    assert not source_cache.exists()
    assert not source_metadata.exists()


def test_organize_incoming_files_removes_orphan_pdf_extractor_metadata(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    orphan_metadata = root / "_incoming" / "project-plan.pdf.extractor.json"
    orphan_metadata.parent.mkdir(parents=True)
    orphan_metadata.write_text('{"parser":"pdf:mineru"}', encoding="utf-8")

    report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")

    assert report.scanned == 1
    assert report.skipped == 1
    assert report.files[0].reason == "removed orphan extractor metadata"
    assert not orphan_metadata.exists()


def test_organize_incoming_files_skips_same_named_duplicate_content(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    target = root / "history" / "tunnel" / "project-plan.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 fake")
    source = root / "_incoming" / "project-plan.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(target.read_bytes())
    source.with_name(f"{source.name}.mineru.md").write_text("# project plan", encoding="utf-8")
    source.with_name(f"{source.name}.extractor.json").write_text('{"parser":"pdf:mineru"}', encoding="utf-8")

    report = organize_incoming_files(
        KnowledgeOrganizeOptions(
            default_category="history",
            default_domain="tunnel",
            category_rules=(),
            domain_rules=(),
        ),
        user_id="alice",
    )

    assert report.moved == 0
    assert report.skipped == 1
    assert report.files[0].reason == "duplicate content"
    assert not source.exists()
    assert not source.with_name(f"{source.name}.mineru.md").exists()
    assert not source.with_name(f"{source.name}.extractor.json").exists()
    assert not (target.parent / "project-plan_1.pdf").exists()


def test_organize_then_build_index_uses_categorized_paths(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "团队专利成果.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 团队专利成果\n\n## 代表性专利\n\n专利列表。", encoding="utf-8")

    organize_report = organize_incoming_files(KnowledgeOrganizeOptions(), user_id="alice")
    build_report = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path=""),
        user_id="alice",
    )

    assert organize_report.files[0].category == "团队成果"
    assert build_report.document_entries == 1
    assert build_report.section_entries >= 1
    assert build_report.entries[0].category == "团队成果"
    assert build_report.entries[0].file_path == "团队成果/通用/团队专利成果.md"
    assert (root / "index.json").exists()


def test_build_knowledge_index_from_folder_updates_existing_entry(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "已有研究基础" / "智能制造基础.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 智能制造基础\n\n旧内容。\n", encoding="utf-8")

    first = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="已有研究基础"), user_id="alice")
    source.write_text("# 智能制造基础更新\n\n新内容。\n", encoding="utf-8")
    second = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="已有研究基础"), user_id="alice")

    assert first.created == 1
    assert second.updated == 1
    assert second.entries[0].index_id == first.entries[0].index_id
    assert second.entries[0].title == "智能制造基础更新"


def test_build_index_backs_up_versions_and_removes_stale_paths(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)
    create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="旧路径申报书",
            category="历史申报书",
            domain="路基工程",
            file_path="旧路径申报书.md",
            summary="旧索引。",
        ),
        user_id="alice",
    )
    source = root / "历史申报书" / "路基工程" / "新路径申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 新路径申报书\n\n## 1.3 国内外研究现状\n\n路基检测现状。", encoding="utf-8")

    response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path=""),
        user_id="alice",
    )

    assert response.deleted == 1
    assert response.version_backup_path is not None
    assert (root / response.version_backup_path).exists()
    assert (root / ".index_versions" / "manifest.json").exists()
    stored_paths = [entry.file_path for entry in knowledge_storage.get_knowledge_storage().list_indexes(user_id="alice")]
    assert "旧路径申报书.md" not in stored_paths
    assert "历史申报书/路基工程/新路径申报书.md" in stored_paths


def test_section_chunk_search_supports_declaration_blocks(tmp_path: Path) -> None:
    source = tmp_path / "knowledge_base" / "历史申报书" / "路基工程" / "现场填方材料力学特性测试理论及路基质量评估方法研究V2.0.docx"
    _write_minimal_docx(
        source,
        [
            "现场填方材料力学特性测试理论及路基质量评估方法研究V2.0",
            "1.3 国内外研究现状",
            "Hertz碰撞理论与Vesic扩张理论用于落球检测和路基质量评估。",
            "1.3.2 路基填方施工质量现场检测技术研究现状",
            "路基填方施工质量现场检测技术用于压实度、回弹模量和施工质量评价。",
            "2．项目的研究内容、研究目标，以及拟解决的关键科学问题",
            "主要研究内容包括填方材料变形模量、回弹模量和现场检测验证。",
            "3.2 技术路线",
            "技术路线包括理论建模、装备开发、现场检测和对比验证。",
        ],
    )
    build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="历史申报书"), user_id="alice")

    status = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="Hertz Vesic 落球检测",
            applicable_chapters=["domestic_foreign_status"],
            limit=5,
        ),
        user_id="alice",
    )
    research = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="填方材料 回弹模量 研究内容",
            applicable_chapters=["research_content"],
            limit=5,
        ),
        user_id="alice",
    )
    route = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="理论建模 现场检测 技术路线",
            applicable_chapters=["technical_route"],
            limit=5,
        ),
        user_id="alice",
    )
    natural_status = search_knowledge_index_entries(
        KnowledgeIndexSearchRequest(
            query="查看路基填方施工质量现场检测技术的研究现状",
            applicable_chapters=["domestic_foreign_status"],
            limit=5,
        ),
        user_id="alice",
    )

    assert status.count >= 1
    assert status.results[0].entry.entry_type in {"section", "subsection"}
    assert "domestic_foreign_status" in status.results[0].entry.proposal_sections
    assert "Hertz" in status.results[0].entry.technical_terms
    assert research.count >= 1
    assert "research_content" in research.results[0].entry.proposal_sections
    assert route.count >= 1
    assert "technical_route" in route.results[0].entry.proposal_sections
    assert natural_status.count >= 1
    assert any(result.entry.source_anchor == "1.3.2 路基填方施工质量现场检测技术研究现状" for result in natural_status.results)


def test_heading_blocks_infer_numbered_levels_from_flat_markdown() -> None:
    content = "## 1.3 国内外研究现状\n\n总述。\n\n## 1.3.1 Hertz碰撞理论应用现状\n\nHertz正文。\n\n## 1.3.2 路基填方施工质量现场检测技术研究现状\n\n路基正文。\n\n## 1.4 发展动态分析\n\n发展正文。\n"

    blocks = knowledge_generator._extract_heading_blocks(content)
    status = next(block for level, heading, block in blocks if heading == "1.3 国内外研究现状")

    assert "Hertz正文" in status
    assert "路基正文" in status
    assert "发展正文" not in status


def test_heading_blocks_keep_fullwidth_number_parent_with_decimal_children() -> None:
    content = (
        "## 3．拟采取的研究方案及可行性分析（包括研究方法、技术路线、实验手段、关键技术等说明）；\n\n"
        "## 3.1 研究方法\n\n"
        "项目采用理论分析、数值模拟和现场测试验证。\n\n"
        "## 3.2 技术路线\n\n"
        "建立填方质量现场快速检测评估技术体系。\n\n"
        "## 4．本项目的特色与创新之处；\n\n"
        "创新内容。\n"
    )

    blocks = knowledge_generator._extract_heading_blocks(content)
    parent = next(block for level, heading, block in blocks if heading.startswith("3．拟采取的研究方案"))

    assert "## 3.1 研究方法" in parent
    assert "## 3.2 技术路线" in parent
    assert "## 4．本项目的特色与创新之处" not in parent


def test_semantic_chunk_candidates_use_parent_summary_and_leaf_evidence() -> None:
    long_leaf = "检测参数、缺陷识别和模型验证。" * 260
    content = (
        "## 研究方案\n\n"
        "本节说明总体实施方案。\n\n"
        "### 多源物探设备搭载与作业适应性研究\n\n"
        "本小节概述设备搭载方案。\n\n"
        "#### 冲击回波检测系统理论参数构建\n\n"
        f"{long_leaf}\n\n"
        "#### 冲击回波检测系统硬件设计\n\n"
        "硬件设计包括激振、采集和同步控制。\n"
    )

    candidates = knowledge_generator._build_semantic_chunk_candidates(content, "历史申报书")

    summaries = [candidate for candidate in candidates if candidate.chunk_kind == "parent_summary"]
    evidence = [candidate for candidate in candidates if candidate.chunk_kind == "leaf_evidence"]
    split_leaf = [candidate for candidate in evidence if candidate.source_anchor == "冲击回波检测系统理论参数构建"]

    assert summaries
    assert all(len(candidate.content) < 1600 for candidate in summaries)
    assert "检测参数、缺陷识别和模型验证。" not in summaries[0].content
    assert len(split_leaf) >= 2
    assert all(candidate.content_role in {"method_design", "problem"} for candidate in split_leaf)
    assert all(len(candidate.content) <= 3400 for candidate in split_leaf)
    assert all(candidate.proposal_sections[0] in {"technical_solution", "research_content"} for candidate in split_leaf)


def test_semantic_chunk_candidates_filter_report_front_matter() -> None:
    content = (
        "## 研 究 报 告\n\n"
        "报告名称：基桩数字信息化检测及数据分析系统\n\n"
        "主持单位：四川蜀工公路工程试验检测有限公司\n\n"
        "编制单位：四川升拓检测技术股份有限公司\n\n"
        "## 目 录\n\n"
        "0 引言....1\n"
        "1 项目背景及现状研究....2\n"
        "1.1 项目概述....2\n"
        "1.2 项目背景....3\n"
        "1.3 国内外研究现状....4\n"
        "2 多厂商跨孔超声基桩检测数据导出程序开发....10\n\n"
        "## 插 图 清 单\n\n"
        "图 1 系统架构图....12\n"
        "图 2 数据流程图....14\n\n"
        "## 附 表 清 单\n\n"
        "表 1 技术指标表....20\n"
        "表 2 成果清单....21\n\n"
        "## 1 项目背景及现状研究\n\n"
        "项目背景。\n\n"
        "## 1.1 项目背景\n\n"
        "基桩检测数字化系统面临数据格式不统一、首波识别依赖人工、分析结果难追溯等问题，"
        "需要通过数据标准化、自动识别算法和可视化系统提升检测效率与质量管控能力。"
        "该研究内容能够支撑工程检测信息化、质量监管和后续项目申报中的技术依据描述。\n"
    )

    candidates = knowledge_generator._build_semantic_chunk_candidates(content, "历史申报书")
    headings = [candidate.heading for candidate in candidates]
    compact_headings = ["".join(heading.split()) for heading in headings]

    assert "研究报告" not in compact_headings
    assert "目录" not in compact_headings
    assert "插图清单" not in compact_headings
    assert "附表清单" not in compact_headings
    assert not any("项目背景及现状研究" in heading for heading in headings)
    assert any(heading.endswith("项目背景") for heading in headings)


def test_build_knowledge_index_skips_root_readme(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Knowledge Base\n\n说明文件。", encoding="utf-8")
    source = root / "历史申报书" / "路基工程" / "申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 申报书\n\n正文。", encoding="utf-8")

    response = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path=""), user_id="alice")

    assert response.scanned_files == 1
    assert response.document_entries == 1
    assert response.entries[0].file_path == "历史申报书/路基工程/申报书.md"


def test_build_index_preserves_existing_category_for_root_files(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "路基质量评估申报书.md"
    root.mkdir(parents=True)
    source.write_text("# 路基质量评估申报书\n\n旧内容。", encoding="utf-8")

    first = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="", category="历史申报书", domain="路基工程"),
        user_id="alice",
    )
    source.write_text("# 路基质量评估申报书更新\n\n新内容。", encoding="utf-8")
    second = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path=""), user_id="alice")

    assert first.created == 1
    assert second.updated == 1
    assert second.entries[0].category == "历史申报书"
    assert second.entries[0].domain == "路基工程"


def test_knowledge_router_build_index(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "团队成果" / "论文成果.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 论文成果\n\n团队论文成果摘要。\n\n## 代表性论文\n\n论文列表。\n", encoding="utf-8")

    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/index/build",
            json={"folder_path": "团队成果"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["document_entries"] == 1
    assert data["section_entries"] >= 1
    assert data["entries"][0]["category"] == "团队成果"
    assert data["entries"][0]["file_path"] == "团队成果/论文成果.md"


def test_knowledge_router_uploads_to_incoming_and_downloads_file(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/knowledge/files/upload",
            files={"files": ("团队成果.md", b"# \xe5\x9b\xa2\xe9\x98\x9f\xe6\x88\x90\xe6\x9e\x9c\n\n\xe6\xad\xa3\xe6\x96\x87\xe3\x80\x82", "text/markdown")},
        )
        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        assert upload_data["files"][0]["file_path"] == "_incoming/团队成果.md"
        assert (tmp_path / "knowledge_base" / "_incoming" / "团队成果.md").exists()

        download_response = client.get(
            "/api/knowledge/files/download",
            params={"file_path": "_incoming/团队成果.md"},
        )

    assert download_response.status_code == 200
    assert "# 团队成果" in download_response.content.decode("utf-8")


def test_knowledge_router_delete_source_file_cleans_chunks_indexes_and_caches(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "历史申报书" / "隧洞检测" / "隧洞检测研究方案.pdf"
    chunk = root / "申报书章节分块" / "技术方案" / "隧洞检测研究方案" / "冲击回波检测.md"
    source.parent.mkdir(parents=True)
    chunk.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")
    source.with_suffix(".pdf.mineru.md").write_text("# 隧洞检测研究方案", encoding="utf-8")
    incoming_cache = root / "_incoming" / "隧洞检测研究方案.pdf.mineru.md"
    incoming_cache.parent.mkdir(parents=True)
    incoming_cache.write_text("# 隧洞检测研究方案", encoding="utf-8")
    chunk.write_text(
        "---\nsource_file: 历史申报书/隧洞检测/隧洞检测研究方案.pdf\n---\n\n## 冲击回波检测\n\n正文。",
        encoding="utf-8",
    )

    document_entry = create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="隧洞检测研究方案",
            category="历史申报书",
            domain="隧洞检测",
            file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
            source_file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
        ),
        user_id="alice",
    )
    chunk_entry = create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="冲击回波检测",
            entry_type="section",
            category="历史申报书",
            domain="隧洞检测",
            file_path="申报书章节分块/技术方案/隧洞检测研究方案/冲击回波检测.md",
            source_file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
            source_anchor="1）冲击回波检测",
        ),
        user_id="alice",
    )

    app = FastAPI()
    app.include_router(knowledge.router)
    with TestClient(app) as client:
        response = client.delete(
            "/api/knowledge/files",
            params={"file_path": "历史申报书/隧洞检测/隧洞检测研究方案.pdf"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_index_entries"] == 2
    assert document_entry.index_id in data["deleted_index_ids"]
    assert chunk_entry.index_id in data["deleted_index_ids"]
    assert data["version_backup_path"]
    assert not source.exists()
    assert not source.with_suffix(".pdf.mineru.md").exists()
    assert not incoming_cache.exists()
    assert not chunk.exists()
    stored_ids = {entry.index_id for entry in knowledge_storage.get_knowledge_storage().list_indexes(user_id="alice")}
    assert document_entry.index_id not in stored_ids
    assert chunk_entry.index_id not in stored_ids


def test_knowledge_router_delete_chunk_preserves_source_file_and_document_index(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "历史申报书" / "隧洞检测" / "隧洞检测研究方案.pdf"
    chunk = root / "申报书章节分块" / "技术方案" / "隧洞检测研究方案" / "冲击回波检测.md"
    source.parent.mkdir(parents=True)
    chunk.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")
    chunk.write_text(
        "---\nsource_file: 历史申报书/隧洞检测/隧洞检测研究方案.pdf\n---\n\n## 冲击回波检测\n\n正文。",
        encoding="utf-8",
    )

    document_entry = create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="隧洞检测研究方案",
            category="历史申报书",
            domain="隧洞检测",
            file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
            source_file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
        ),
        user_id="alice",
    )
    chunk_entry = create_knowledge_index_entry(
        KnowledgeIndexEntryCreate(
            title="冲击回波检测",
            entry_type="section",
            category="历史申报书",
            domain="隧洞检测",
            file_path="申报书章节分块/技术方案/隧洞检测研究方案/冲击回波检测.md",
            source_file_path="历史申报书/隧洞检测/隧洞检测研究方案.pdf",
            source_anchor="1）冲击回波检测",
        ),
        user_id="alice",
    )

    app = FastAPI()
    app.include_router(knowledge.router)
    with TestClient(app) as client:
        response = client.delete(
            "/api/knowledge/files",
            params={
                "file_path": "申报书章节分块/技术方案/隧洞检测研究方案/冲击回波检测.md",
                "delete_source": "false",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["deleted_index_entries"] == 1
    assert data["deleted_index_ids"] == [chunk_entry.index_id]
    assert source.exists()
    assert not chunk.exists()
    stored_ids = {entry.index_id for entry in knowledge_storage.get_knowledge_storage().list_indexes(user_id="alice")}
    assert document_entry.index_id in stored_ids
    assert chunk_entry.index_id not in stored_ids


def test_knowledge_router_warns_when_uploading_word_file(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        upload_response = client.post(
            "/api/knowledge/files/upload",
            files={
                "files": (
                    "项目申报书.docx",
                    b"fake docx body",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert upload_response.status_code == 200
    data = upload_response.json()
    assert data["files"][0]["file_path"] == "_incoming/项目申报书.docx"
    assert any("建议" in warning and "PDF" in warning for warning in data["warnings"])


def test_process_incoming_endpoint_organizes_and_builds_index(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "路基项目申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 路基项目申报书\n\n## 1.3 国内外研究现状\n\n路基质量评估研究现状。", encoding="utf-8")

    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/index/process-incoming",
            json={
                "incoming_path": "_incoming",
                "folder_path": "",
                "default_category": "未分类",
                "default_domain": "通用",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["organization"]["moved"] == 1
    assert data["index_build"]["document_entries"] == 1
    assert data["index_build"]["section_entries"] >= 1
    assert (root / "index.json").exists()
    assert not source.exists()


def test_build_index_deduplicates_word_when_same_pdf_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "knowledge_base"
    docx = root / "历史申报书" / "路基工程" / "现场填方材料力学特性测试理论及路基质量评估方法研究V2.0.docx"
    pdf = docx.with_suffix(".pdf")
    _write_minimal_docx(
        docx,
        [
            "现场填方材料力学特性测试理论及路基质量评估方法研究V2.0",
            "1.3 国内外研究现状",
            "Word版本研究现状。",
        ],
    )
    first = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="历史申报书"), user_id="alice")
    assert first.document_entries == 1
    assert first.entries[0].file_path.endswith(".docx")

    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(
        knowledge_extractors,
        "_parse_pdf_with_mineru",
        lambda path: "# 现场填方材料力学特性测试理论及路基质量评估方法研究V2.0\n\n## 1.3 国内外研究现状\n\nPDF版本研究现状。\n\n## 2.1 研究内容\n\nPDF版本研究内容。",
    )

    second = build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="历史申报书"), user_id="alice")

    stored_paths = [entry.file_path for entry in knowledge_storage.get_knowledge_storage().list_indexes(user_id="alice")]
    assert docx.relative_to(root).as_posix() in second.deduplicated_files
    assert all(not path.endswith(".docx") for path in stored_paths)
    assert any(path.endswith(".pdf") for path in stored_paths)
    assert second.skipped >= 1
    assert second.deleted >= 1


def test_build_index_supports_docx_numbered_headings(tmp_path: Path) -> None:
    source = tmp_path / "knowledge_base" / "历史申报书" / "交通工程" / "路基质量评估申报书.docx"
    _write_minimal_docx(
        source,
        [
            "报告正文",
            "1．项目的立项依据",
            "1.1 背景及对应科学问题",
            "背景内容。",
            "1.3 国内外研究现状",
            "国内外研究现状正文。",
            "1.3.1 Hertz碰撞理论应用现状",
            "理论应用内容。",
            "2．研究内容",
            "研究内容正文。",
        ],
    )

    build_response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="历史申报书"),
        user_id="alice",
    )

    assert build_response.document_entries == 1
    assert build_response.section_entries >= 2
    entry = build_response.entries[0]
    assert entry.category == "历史申报书"
    assert entry.domain == "交通工程"
    assert entry.file_path == "历史申报书/交通工程/路基质量评估申报书.docx"
    assert "历史申报书" in entry.proposal_sections
    status_entry = next(item for item in build_response.entries if item.source_anchor == "1.3 国内外研究现状")
    assert "domestic_foreign_status" in status_entry.proposal_sections
    assert status_entry.file_path.startswith("申报书章节分块/")
    assert (tmp_path / "knowledge_base" / status_entry.file_path).exists()

    read_response = read_knowledge_file(
        KnowledgeFileReadRequest(
            file_path="历史申报书/交通工程/路基质量评估申报书.docx",
            anchor="国内外研究现状",
        ),
        user_id="alice",
    )
    assert "1.3 国内外研究现状" in read_response.content
    assert "理论应用内容" in read_response.content
    assert "2．研究内容" not in read_response.content


def test_section_topic_filename_removes_parenthesized_number_prefix() -> None:
    assert knowledge_generator._section_topic_filename("1）冲击回波检测系统理论参数构建") == "冲击回波检测系统理论参数构建.md"
    assert knowledge_generator._section_topic_filename("（2）冲击回波检测系统硬件设计") == "冲击回波检测系统硬件设计.md"
    assert knowledge_generator._section_topic_filename("三）多源检测信息一致性表征") == "多源检测信息一致性表征.md"


def test_read_knowledge_file_prefers_shortest_fuzzy_heading(tmp_path: Path) -> None:
    source = tmp_path / "knowledge_base" / "历史申报书" / "交通工程" / "路基质量评估申报书.docx"
    _write_minimal_docx(
        source,
        [
            "1．项目的立项依据（研究意义、国内外研究现状及发展动态分析）",
            "上层内容。",
            "1.3 国内外研究现状",
            "目标章节内容。",
            "1.3.1 子章节",
            "子章节内容。",
            "1.4 发展动态分析",
            "后续章节。",
        ],
    )

    response = read_knowledge_file(
        KnowledgeFileReadRequest(
            file_path="历史申报书/交通工程/路基质量评估申报书.docx",
            anchor="国内外研究现状",
        ),
        user_id="alice",
    )

    assert response.content.startswith("## 1.3 国内外研究现状")
    assert "目标章节内容" in response.content
    assert "上层内容" not in response.content
    assert "后续章节" not in response.content


def test_build_index_supports_pdf_via_mineru_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "knowledge_base" / "政策指南" / "省级重点研发指南.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(
        knowledge_extractors,
        "_parse_pdf_with_mineru",
        lambda path: "# 省级重点研发指南\n\n指南摘要。\n\n## 申报条件\n\n申报条件内容。",
    )

    build_response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="政策指南"),
        user_id="alice",
    )

    assert build_response.document_entries == 1
    entry = build_response.entries[0]
    assert entry.category == "政策指南"
    assert entry.file_path == "政策指南/省级重点研发指南.pdf"
    assert any(item.source_anchor == "申报条件" for item in build_response.entries)
    assert source.with_suffix(".pdf.mineru.md").exists()
    assert build_response.parser_counts["pdf:mineru"] == 1
    assert entry.metadata["parser"] == "pdf:mineru"


def test_build_index_falls_back_when_mineru_pdf_parse_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "knowledge_base" / "政策指南" / "省级重点研发指南.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF-1.4 fake")

    def fail_mineru(path: Path) -> str:
        raise RuntimeError("MINERU_API_TOKEN is not set")

    def parse_with_pymupdf(path: Path) -> str:
        return "# 省级重点研发指南\n\n指南摘要。\n\n## 申报条件\n\nfallback 申报条件内容。"

    monkeypatch.setattr(knowledge_extractors, "_parse_pdf_with_mineru", fail_mineru)
    monkeypatch.setattr(knowledge_extractors, "_parse_pdf_with_pymupdf4llm", parse_with_pymupdf)

    build_response = build_knowledge_index_from_folder(
        KnowledgeIndexBuildRequest(folder_path="政策指南"),
        user_id="alice",
    )

    assert build_response.document_entries == 1
    assert build_response.parser_counts["pdf:pymupdf4llm"] == 1
    assert any("pdf:mineru" in warning for warning in build_response.warnings)
    assert build_response.parse_errors == []
    entry = build_response.entries[0]
    assert entry.metadata["parser"] == "pdf:pymupdf4llm"
    assert source.with_suffix(".pdf.mineru.md").exists()


def test_builtin_knowledge_tools_search_and_read(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "国内外研究现状" / "路基工程" / "路基质量评估研究现状.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        "# 路基质量评估研究现状\n\n总述。\n\n## 国内研究现状\n\n路基质量评估国内研究内容。\n\n## 现有问题\n\n问题内容。\n",
        encoding="utf-8",
    )
    build_knowledge_index_from_folder(KnowledgeIndexBuildRequest(folder_path="国内外研究现状"), user_id="alice")

    search_payload = knowledge_search_index_tool.invoke(
        {
            "query": "路基质量评估",
            "categories": ["国内外研究现状"],
            "applicable_chapters": ["国内外研究现状"],
            "domains": ["路基工程"],
            "project_types": None,
            "limit": 5,
        }
    )
    assert "路基质量评估研究现状" in search_payload
    assert "国内外研究现状/路基工程/路基质量评估研究现状.md" in search_payload
    assert "Knowledge index search results." in search_payload
    assert "call knowledge_read_file" in search_payload
    assert '"results"' not in search_payload
    assert '"entry"' not in search_payload

    read_payload = knowledge_read_file_tool.invoke(
        {
            "file_path": "国内外研究现状/路基工程/路基质量评估研究现状.md",
            "anchor": "国内研究现状",
            "max_chars": 2000,
        }
    )
    assert "路基质量评估国内研究内容" in read_payload
    assert "Knowledge source excerpt." in read_payload
    assert "content:" in read_payload
    assert '"content"' not in read_payload
    assert "## 现有问题" not in read_payload


def test_builtin_knowledge_incremental_update_tool(tmp_path: Path) -> None:
    root = tmp_path / "knowledge_base"
    source = root / "_incoming" / "路基项目申报书.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 路基项目申报书\n\n申报书内容。", encoding="utf-8")

    payload = knowledge_incremental_update_tool.invoke(
        {
            "incoming_path": "_incoming",
            "folder_path": "",
            "dry_run": False,
            "default_category": "未分类",
            "default_domain": "通用",
        }
    )

    assert "历史申报书/路基工程/路基项目申报书.md" in payload
    assert (root / "历史申报书" / "路基工程" / "路基项目申报书.md").exists()
    assert (root / "index.json").exists()


def test_available_tools_include_knowledge_tools() -> None:
    app_config = SimpleNamespace(
        tools=[],
        models=[],
        skill_evolution=SimpleNamespace(enabled=False),
        acp_agents={},
    )
    tool_names = {tool.name for tool in get_available_tools(include_mcp=False, app_config=app_config)}

    assert "knowledge_search_index" in tool_names
    assert "knowledge_read_file" in tool_names
    assert "knowledge_list_images" in tool_names
    assert "knowledge_incremental_update" in tool_names
    assert "proposal_save_markdown" in tool_names


def test_proposal_save_markdown_persists_workspace_and_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_root = tmp_path / "proposal_drafts"
    outputs_root = tmp_path / "thread" / "user-data" / "outputs"
    outputs_root.mkdir(parents=True)
    monkeypatch.setattr(
        "deerflow.tools.builtins.proposal_workspace_tool._proposal_workspace_root",
        lambda: workspace_root,
    )
    runtime = SimpleNamespace(state={"thread_data": {"outputs_path": str(outputs_root)}})

    result = proposal_save_markdown_tool.func(
        runtime=runtime,
        task_name="路基质量评估项目",
        section_name="国内外研究现状",
        content="# 国内外研究现状\n\n正文。",
        tool_call_id="call_1",
    )

    workspace_file = workspace_root / "路基质量评估项目" / "国内外研究现状.md"
    artifact_file = outputs_root / "proposal_drafts" / "路基质量评估项目" / "国内外研究现状.md"
    assert workspace_file.read_text(encoding="utf-8") == "# 国内外研究现状\n\n正文。"
    assert artifact_file.read_text(encoding="utf-8") == "# 国内外研究现状\n\n正文。"
    assert result.update["artifacts"] == ["/mnt/user-data/outputs/proposal_drafts/路基质量评估项目/国内外研究现状.md"]


def test_proposal_save_markdown_uses_one_project_folder_per_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "proposal_drafts"
    outputs_root = tmp_path / "thread" / "user-data" / "outputs"
    outputs_root.mkdir(parents=True)
    monkeypatch.setattr(
        "deerflow.tools.builtins.proposal_workspace_tool._proposal_workspace_root",
        lambda: workspace_root,
    )
    runtime = SimpleNamespace(
        state={"thread_data": {"outputs_path": str(outputs_root)}},
        context={"thread_id": "thread-abc-123"},
    )

    proposal_save_markdown_tool.func(
        runtime=runtime,
        task_name="路基质量评估项目",
        section_name="课题规划",
        content="# 课题规划\n",
        tool_call_id="call_1",
    )
    result = proposal_save_markdown_tool.func(
        runtime=runtime,
        task_name="研究方案",
        section_name="技术路线",
        content="# 技术路线\n",
        tool_call_id="call_2",
    )

    project_dir = workspace_root / "路基质量评估项目-thread-a"
    assert (project_dir / "课题规划.md").read_text(encoding="utf-8") == "# 课题规划\n"
    assert (project_dir / "研究方案" / "技术路线.md").read_text(encoding="utf-8") == "# 技术路线\n"
    assert not (workspace_root / "研究方案").exists()
    assert not (workspace_root / ".thread_projects").exists()
    assert result.update["artifacts"] == ["/mnt/user-data/outputs/proposal_drafts/路基质量评估项目-thread-a/研究方案/技术路线.md"]


def test_proposal_save_markdown_uses_project_directory_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = tmp_path / "projects"
    project_id = "project-1"
    project_meta_dir = projects_root / project_id
    custom_root = tmp_path / "selected-project-dir"
    outputs_root = tmp_path / "thread" / "user-data" / "outputs"
    project_meta_dir.mkdir(parents=True)
    outputs_root.mkdir(parents=True)
    (project_meta_dir / ".project.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "name": "申报项目",
                "type": "government-project-declaration",
                "status": "active",
                "root_path": str(custom_root),
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "deerflow.tools.builtins.proposal_workspace_tool.government_project_projects_root",
        lambda: projects_root,
    )
    runtime = SimpleNamespace(
        state={"thread_data": {"outputs_path": str(outputs_root)}},
        context={"project_id": project_id, "project_name": "申报项目"},
    )

    result = proposal_save_markdown_tool.func(
        runtime=runtime,
        task_name="申报项目",
        section_name="技术路线",
        content="# 技术路线\n",
        tool_call_id="call_1",
        subfolder_name="研究方案",
    )

    workspace_file = custom_root / "drafts" / "研究方案" / "技术路线.md"
    assert workspace_file.read_text(encoding="utf-8") == "# 技术路线\n"
    assert not (project_meta_dir / "drafts" / "研究方案" / "技术路线.md").exists()
    assert result.update["artifacts"] == ["/mnt/user-data/outputs/projects/project-1/drafts/研究方案/技术路线.md"]


def test_proposal_drafts_router_lists_reads_and_saves_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    drafts_root = tmp_path / "proposal_drafts"
    draft_file = drafts_root / "路基质量评估项目" / "国内外研究现状.md"
    draft_file.parent.mkdir(parents=True)
    draft_file.write_text("# 国内外研究现状\n\n初稿。", encoding="utf-8")

    monkeypatch.setattr(
        proposal_drafts,
        "government_project_drafts_root",
        lambda: drafts_root,
    )

    app = FastAPI()
    app.include_router(proposal_drafts.router)

    with TestClient(app) as client:
        list_response = client.get("/api/proposal-drafts")
        assert list_response.status_code == 200
        assert list_response.json()["files"][0]["task_name"] == "路基质量评估项目"

        read_response = client.get("/api/proposal-drafts/路基质量评估项目/国内外研究现状")
        assert read_response.status_code == 200
        assert read_response.json()["content"] == "# 国内外研究现状\n\n初稿。"

        save_response = client.put(
            "/api/proposal-drafts/路基质量评估项目/研究方案",
            json={"content": "# 研究方案\n\n修订稿。"},
        )
        assert save_response.status_code == 200
        saved_file = drafts_root / "路基质量评估项目" / "研究方案.md"
        assert saved_file.read_text(encoding="utf-8") == "# 研究方案\n\n修订稿。"

        version_response = client.post("/api/proposal-drafts/versions/路基质量评估项目/研究方案")
        assert version_response.status_code == 200
        version_payload = version_response.json()["version"]
        assert version_payload["section_name"] == "研究方案"
        assert version_payload["file_path"].endswith(".md")

        versions_response = client.get("/api/proposal-drafts/versions/路基质量评估项目/研究方案")
        assert versions_response.status_code == 200
        assert len(versions_response.json()["versions"]) == 1
        version_id = versions_response.json()["versions"][0]["version_id"]

        version_read_response = client.get(
            "/api/proposal-drafts/version-content/路基质量评估项目/研究方案",
            params={"version_id": version_id},
        )
        assert version_read_response.status_code == 200
        assert version_read_response.json()["content"] == "# 研究方案\n\n修订稿。"

        download_response = client.get("/api/proposal-drafts/download/路基质量评估项目/研究方案")
        assert download_response.status_code == 200
        assert download_response.content.decode("utf-8").replace("\r\n", "\n") == "# 研究方案\n\n修订稿。"

        nested_response = client.put(
            "/api/proposal-drafts/路基质量评估项目/研究方案/技术路线",
            json={"content": "# 技术路线\n\n分层草稿。"},
        )
        assert nested_response.status_code == 200
        nested_file = drafts_root / "路基质量评估项目" / "研究方案" / "技术路线.md"
        assert nested_file.read_text(encoding="utf-8") == "# 技术路线\n\n分层草稿。"

        nested_read_response = client.get("/api/proposal-drafts/路基质量评估项目/研究方案/技术路线")
        assert nested_read_response.status_code == 200
        assert nested_read_response.json()["section_name"] == "研究方案/技术路线"

        list_after_version_response = client.get("/api/proposal-drafts")
        assert list_after_version_response.status_code == 200
        assert all(".history" not in item["file_path"] for item in list_after_version_response.json()["files"])
        assert any(item["section_name"] == "研究方案/技术路线" for item in list_after_version_response.json()["files"])

        delete_response = client.delete("/api/proposal-drafts/路基质量评估项目/研究方案")
        assert delete_response.status_code == 204
        assert not saved_file.exists()

        traversal_response = client.get("/api/proposal-drafts/../secret")
        assert traversal_response.status_code == 404
