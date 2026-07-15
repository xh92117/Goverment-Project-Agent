import io
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from PIL import Image

from deerflow.knowledge import assets as knowledge_assets
from deerflow.knowledge import storage as knowledge_storage
from deerflow.knowledge.export_images import (
    ExportEvidenceDocument,
    NoRelevantImageEvidenceError,
    NoVerifiedImageEvidenceError,
    enrich_export_documents_with_images,
)
from deerflow.knowledge.schemas import KnowledgeEvidencePatch


@pytest.fixture(autouse=True)
def isolated_knowledge_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "knowledge_base"
    monkeypatch.setattr(knowledge_storage, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_storage, "_knowledge_file_path", lambda *, user_id=None: root / "index.json")
    monkeypatch.setattr(knowledge_storage, "_storage_instance", knowledge_storage.FileKnowledgeBaseStorage())
    yield
    monkeypatch.setattr(knowledge_storage, "_storage_instance", None)


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 20), color=color).save(output, format="PNG")
    return output.getvalue()


def _create_evidence(*, title: str, verified: bool, color: tuple[int, int, int]) -> str:
    _asset, evidence, _duplicate = knowledge_assets.ingest_knowledge_image(
        _png_bytes(color),
        filename=f"{title}.png",
        applicant_id="default",
        title=title,
        evidence_type="qualification_certificate",
        user_id="alice",
    )
    if verified:
        evidence = knowledge_assets.update_knowledge_evidence(
            evidence.evidence_id,
            KnowledgeEvidencePatch(
                holder="Example Technology Co., Ltd.",
                issuer="Review Authority",
                verification_status="human_verified",
                keywords=[title, "qualification"],
            ),
            applicant_id="default",
            user_id="alice",
        )
    return evidence.evidence_id


@pytest.mark.asyncio
async def test_export_agent_only_sees_verified_evidence_and_assigns_it_to_relevant_document() -> None:
    verified_id = _create_evidence(title="Business License", verified=True, color=(24, 96, 160))
    unreviewed_id = _create_evidence(title="Unreviewed Award", verified=False, color=(160, 96, 24))
    captured: dict[str, object] = {}

    class FakeModel:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return AIMessage(content=(f'{{"assignments":[{{"document_index":0,"evidence_ids":["{verified_id}"]}}]}}'))

    result = await enrich_export_documents_with_images(
        [
            ExportEvidenceDocument(title="Applicant foundation", content="The applicant has valid corporate qualifications."),
            ExportEvidenceDocument(title="Budget", content="Equipment and testing budget."),
        ],
        applicant_id="default",
        model_name="selector-model",
        user_id="alice",
        model_factory=lambda **kwargs: FakeModel(),
    )

    prompt = captured["messages"][1].content
    assert verified_id in prompt
    assert unreviewed_id not in prompt
    assert f"evidence://default/{verified_id}" in result.markdowns[0]
    assert result.markdowns[1] == "Equipment and testing budget."
    assert result.evidence_count == 1
    assert result.model_name == "selector-model"


@pytest.mark.asyncio
async def test_export_agent_requires_verified_evidence() -> None:
    _create_evidence(title="Pending License", verified=False, color=(24, 160, 96))

    with pytest.raises(NoVerifiedImageEvidenceError):
        await enrich_export_documents_with_images(
            [ExportEvidenceDocument(title="Foundation", content="Applicant qualification")],
            applicant_id="default",
            model_name="selector-model",
            user_id="alice",
            model_factory=lambda **kwargs: pytest.fail("model must not run without verified evidence"),
        )


@pytest.mark.asyncio
async def test_export_agent_reports_when_no_evidence_is_relevant() -> None:
    _create_evidence(title="Business License", verified=True, color=(96, 24, 160))

    class FakeModel:
        async def ainvoke(self, messages):
            return AIMessage(content='{"assignments":[]}')

    with pytest.raises(NoRelevantImageEvidenceError):
        await enrich_export_documents_with_images(
            [ExportEvidenceDocument(title="Budget", content="Travel budget only")],
            applicant_id="default",
            model_name="selector-model",
            user_id="alice",
            model_factory=lambda **kwargs: FakeModel(),
        )
