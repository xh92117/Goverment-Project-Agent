import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from PIL import Image

from app.gateway.docx_export import build_conversation_docx, build_markdown_docx
from deerflow.knowledge import assets as knowledge_assets
from deerflow.knowledge import storage as knowledge_storage
from deerflow.knowledge.schemas import KnowledgeEvidencePatch


@pytest.fixture(autouse=True)
def isolated_knowledge_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "knowledge_base"
    monkeypatch.setattr(knowledge_storage, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_storage, "_knowledge_file_path", lambda *, user_id=None: root / "index.json")
    monkeypatch.setattr(knowledge_storage, "_storage_instance", knowledge_storage.FileKnowledgeBaseStorage())
    yield
    monkeypatch.setattr(knowledge_storage, "_storage_instance", None)


def _image_bytes(*, image_format: str = "PNG") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (240, 160), color=(24, 96, 160)).save(output, format=image_format)
    return output.getvalue()


def _create_evidence(*, applicant_id: str = "default", verified: bool) -> str:
    _asset, evidence, _duplicate = knowledge_assets.ingest_knowledge_image(
        _image_bytes(),
        filename="business-license.png",
        applicant_id=applicant_id,
        evidence_type="qualification_certificate",
        title="Business License",
        user_id="alice",
    )
    if verified:
        evidence = knowledge_assets.update_knowledge_evidence(
            evidence.evidence_id,
            KnowledgeEvidencePatch(
                holder="Example Technology Co., Ltd.",
                issuer="Market Supervision Administration",
                verification_status="human_verified",
            ),
            applicant_id=applicant_id,
            user_id="alice",
        )
    return evidence.evidence_id


def _package_parts(data: bytes) -> tuple[list[str], str]:
    with ZipFile(io.BytesIO(data)) as archive:
        return archive.namelist(), archive.read("word/document.xml").decode("utf-8")


def test_verified_evidence_uri_is_embedded_in_docx() -> None:
    evidence_id = _create_evidence(verified=True)

    data = build_markdown_docx(
        "Proposal",
        f"# Existing foundation\n\n![Business License](evidence://default/{evidence_id})",
    )

    names, document_xml = _package_parts(data)
    assert [name for name in names if name.startswith("word/media/")] == ["word/media/image1.png"]
    assert "<w:drawing>" in document_xml
    assert "Business License" in document_xml


def test_unreviewed_or_wrong_applicant_evidence_is_not_embedded() -> None:
    unreviewed_id = _create_evidence(verified=False)
    other_applicant_id = _create_evidence(applicant_id="org-002", verified=True)

    data = build_markdown_docx(
        "Proposal",
        "\n".join(
            [
                f"![Unreviewed](evidence://default/{unreviewed_id})",
                f"![Wrong applicant](evidence://default/{other_applicant_id})",
            ]
        ),
    )

    names, document_xml = _package_parts(data)
    assert not any(name.startswith("word/media/") for name in names)
    assert "<w:drawing>" not in document_xml


def test_verified_evidence_citation_adds_one_attachment_and_hides_internal_id() -> None:
    evidence_id = _create_evidence(verified=True)

    data = build_markdown_docx(
        "Proposal",
        (
            "The applicant is legally registered. "
            f"【Knowledge Base: Business License | evidence:{evidence_id}】\n\n"
            f"The same evidence is cited again: evidence:{evidence_id}."
        ),
    )

    names, document_xml = _package_parts(data)
    assert [name for name in names if name.startswith("word/media/")] == ["word/media/image1.png"]
    assert evidence_id not in document_xml
    assert "相关证明材料" in document_xml


def test_verified_webp_evidence_is_converted_and_embedded_as_png() -> None:
    asset, evidence, _duplicate = knowledge_assets.ingest_knowledge_image(
        _image_bytes(image_format="WEBP"),
        filename="award.webp",
        applicant_id="default",
        evidence_type="honor_certificate",
        title="Innovation Award",
        user_id="alice",
    )
    evidence = knowledge_assets.update_knowledge_evidence(
        evidence.evidence_id,
        KnowledgeEvidencePatch(
            holder="Example Technology Co., Ltd.",
            issuer="Technology Association",
            verification_status="human_verified",
        ),
        applicant_id="default",
        user_id="alice",
    )

    data = build_markdown_docx(
        "Proposal",
        f"![Innovation Award](evidence://default/{evidence.evidence_id})",
    )

    names, _document_xml = _package_parts(data)
    assert "word/media/image1.png" in names
    with ZipFile(io.BytesIO(data)) as archive:
        with Image.open(io.BytesIO(archive.read("word/media/image1.png"))) as embedded:
            assert embedded.format == "PNG"
    assert asset.mime_type == "image/webp"


def test_conversation_export_embeds_verified_cited_evidence() -> None:
    evidence_id = _create_evidence(verified=True)

    data = build_conversation_docx(
        "Proposal discussion",
        [
            {
                "role": "assistant",
                "content": f"Verified applicant qualification. evidence:{evidence_id}",
            }
        ],
    )

    names, document_xml = _package_parts(data)
    assert [name for name in names if name.startswith("word/media/")] == ["word/media/image1.png"]
    assert evidence_id not in document_xml
