import io
import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import proposal_drafts
from app.gateway.routers.exports import ExportMessage, _build_docx


def test_conversation_docx_uses_required_declaration_format() -> None:
    table = chr(0x8868)
    figure = chr(0x56FE)
    colon = chr(0xFF1A)
    content = (
        "# 一级标题\n"
        "## 二级标题\n"
        "### 三级标题\n"
        "正文段落\n"
        f"{table}1{colon}表题\n"
        f"{figure}1{colon}图题"
    )

    data = _build_docx(
        "申报书导出",
        [ExportMessage(role="assistant", content=content)],
    )

    archive = zipfile.ZipFile(io.BytesIO(data))
    document_xml = archive.read("word/document.xml").decode("utf-8")
    styles_xml = archive.read("word/styles.xml").decode("utf-8")
    numbering_xml = archive.read("word/numbering.xml").decode("utf-8")

    assert "黑体" in document_xml
    assert "仿宋" in document_xml
    assert 'w:firstLine="480"' in document_xml
    assert 'w:line="360"' in document_xml
    assert 'w:line="240"' in document_xml
    assert 'w:sz w:val="32"' in document_xml
    assert 'w:sz w:val="24"' in document_xml
    assert 'w:sz w:val="21"' in document_xml
    assert "Times New Roman" in document_xml
    assert '<w:pStyle w:val="Heading1"/>' in document_xml
    assert '<w:pStyle w:val="Heading2"/>' in document_xml
    assert '<w:pStyle w:val="Heading3"/>' in document_xml
    assert '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:style w:type="paragraph" w:styleId="Heading1">' in styles_xml
    assert '<w:style w:type="paragraph" w:styleId="Heading2">' in styles_xml
    assert '<w:style w:type="paragraph" w:styleId="Heading3">' in styles_xml
    assert 'w:lvlText w:val="%1"' in numbering_xml
    assert 'w:lvlText w:val="%1.%2"' in numbering_xml
    assert 'w:lvlText w:val="%1.%2.%3"' in numbering_xml
    assert "2 一级标题" not in document_xml
    assert "2.1 二级标题" not in document_xml
    assert "2.1.1 三级标题" not in document_xml


def test_draft_docx_download_uses_default_word_format(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(proposal_drafts, "_drafts_root", lambda: tmp_path)
    draft = tmp_path / "项目A" / "技术路线.md"
    draft.parent.mkdir(parents=True)
    draft.write_text(
        "# 一、一级标题\n"
        "## 1.1 二级标题\n"
        "---\n"
        "### （一）三级标题\n"
        "正文 ABC 123 和 $x+y$。\n\n"
        "表1：表题\n"
        "| 指标 | 数值 |\n"
        "| --- | --- |\n"
        "| A | 1 |\n\n"
        "图1：图题\n"
        "$$E=mc^2$$\n",
        encoding="utf-8",
    )

    app = FastAPI()
    app.include_router(proposal_drafts.router)
    response = TestClient(app).get("/api/proposal-drafts/download-docx/项目A/技术路线")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    document_xml = archive.read("word/document.xml").decode("utf-8")
    styles_xml = archive.read("word/styles.xml").decode("utf-8")
    numbering_xml = archive.read("word/numbering.xml").decode("utf-8")

    assert '<w:pStyle w:val="Heading1"/>' in document_xml
    assert '<w:pStyle w:val="Heading2"/>' in document_xml
    assert '<w:pStyle w:val="Heading3"/>' in document_xml
    assert '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:numPr><w:ilvl w:val="1"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:numPr><w:ilvl w:val="2"/><w:numId w:val="1"/></w:numPr>' in document_xml
    assert '<w:style w:type="paragraph" w:styleId="Heading1">' in styles_xml
    assert 'w:lvlText w:val="%1"' in numbering_xml
    assert 'w:lvlText w:val="%1.%2"' in numbering_xml
    assert 'w:lvlText w:val="%1.%2.%3"' in numbering_xml
    assert "一级标题" in document_xml
    assert "二级标题" in document_xml
    assert "三级标题" in document_xml
    assert "一、一级标题" not in document_xml
    assert "1.1 二级标题" not in document_xml
    assert "（一）三级标题" not in document_xml
    assert "<w:t xml:space=\"preserve\">---</w:t>" not in document_xml
    assert 'w:rFonts w:ascii="Times New Roman"' in document_xml
    assert 'w:firstLine="480"' in document_xml
    assert 'w:line="360"' in document_xml
    assert 'w:line="240"' in document_xml
    assert '<w:tbl>' in document_xml
    assert 'w:jc w:val="center"' in document_xml
    assert "m:oMath" in document_xml
