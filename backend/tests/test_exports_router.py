from __future__ import annotations

import io
from zipfile import ZipFile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import exports


def test_conversation_export_endpoint_accepts_word_format() -> None:
    app = FastAPI()
    app.include_router(exports.router)

    with TestClient(app) as client:
        response = client.post(
            "/api/exports/conversation.docx",
            json={
                "title": "对话导出",
                "messages": [{"role": "assistant", "content": "# 研究总结\n\n正文内容。"}],
                "word_format": {
                    "body_font": "宋体",
                    "body_font_size_pt": 14,
                    "line_spacing": 2,
                    "heading_font": "楷体",
                    "heading_start_level": 2,
                },
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with ZipFile(io.BytesIO(response.content)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")
    assert '<w:pStyle w:val="Heading2"/>' in document_xml
    assert 'w:eastAsia="宋体"' in document_xml
    assert 'w:eastAsia="楷体"' in document_xml
    assert 'w:line="480"' in document_xml
