from pathlib import Path

import pytest
import yaml

from deerflow.knowledge import (
    KnowledgeIndexEntryCreate,
    KnowledgeRecallEvalCase,
    KnowledgeRecallEvalRequest,
    create_knowledge_index_entry,
    evaluate_knowledge_recall,
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
    yield
    monkeypatch.setattr(knowledge_storage, "_storage_instance", None)


def test_no_embedding_knowledge_retrieval_golden_set() -> None:
    fixture_path = Path(__file__).parent / "evals" / "knowledge_retrieval_cases.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    for payload in fixture["index_entries"]:
        create_knowledge_index_entry(KnowledgeIndexEntryCreate(**payload), user_id="alice")

    response = evaluate_knowledge_recall(
        KnowledgeRecallEvalRequest(
            cases=[KnowledgeRecallEvalCase(**case) for case in fixture["cases"]],
            limit=5,
            search_mode="keyword",
        ),
        user_id="alice",
    )

    assert response.total_cases == 8
    assert response.recall_at_k == 1.0
    assert response.mrr >= 0.9
    assert response.forbidden_hit_count == 0
    assert response.contamination_rate == 0.0
