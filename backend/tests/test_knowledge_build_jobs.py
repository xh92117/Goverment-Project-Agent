from __future__ import annotations

import threading
from pathlib import Path
from time import sleep

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import knowledge as knowledge_router
from deerflow.knowledge import generator as knowledge_generator
from deerflow.knowledge import storage as knowledge_storage
from deerflow.knowledge.build_jobs import (
    KnowledgeBuildJobConflictError,
    KnowledgeBuildJobManager,
)
from deerflow.knowledge.quality import evaluate_knowledge_build_quality
from deerflow.knowledge.schemas import (
    KnowledgeIndexBuildRequest,
    KnowledgeIndexBuildResponse,
    KnowledgeIndexEntry,
)


@pytest.fixture
def knowledge_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "knowledge"
    monkeypatch.setattr(knowledge_storage, "_knowledge_file_path", lambda *, user_id=None: root / "index.json")
    monkeypatch.setattr(knowledge_storage, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_generator, "_knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr("deerflow.knowledge.build_jobs._knowledge_root_path", lambda *, user_id=None: root)
    monkeypatch.setattr(knowledge_storage, "_storage_instance", knowledge_storage.FileKnowledgeBaseStorage())
    return root


def _entry(
    index_id: str,
    file_path: str,
    *,
    entry_type: str = "section",
    metadata: dict[str, object] | None = None,
) -> KnowledgeIndexEntry:
    return KnowledgeIndexEntry(
        index_id=index_id,
        title=Path(file_path).stem,
        entry_type=entry_type,
        category="通用资料",
        file_path=file_path,
        source_file_path="source.md",
        metadata=metadata or {},
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def test_quality_gate_detects_empty_bodies_broken_assets_and_chunk_links(knowledge_root: Path) -> None:
    knowledge_root.mkdir()
    (knowledge_root / "source.md").write_text("# 源文件\n\n正文。", encoding="utf-8")
    (knowledge_root / "chunk.md").write_text(
        "---\nsource_file: source.md\n---\n\n## 分块\n\n![缺失图片](knowledge-file://missing.png)",
        encoding="utf-8",
    )
    entries = [
        _entry("idx_missing", "missing.md", entry_type="document"),
        _entry(
            "idx_chunk",
            "chunk.md",
            metadata={
                "chunk_kind": "leaf_evidence",
                "chunk_id": "chunk-1",
                "chunk_group_id": "group-1",
                "chunk_sequence": 1,
                "chunk_count": 2,
                "previous_chunk_id": None,
                "next_chunk_id": "missing-chunk",
            },
        ),
    ]

    report = evaluate_knowledge_build_quality(entries, root=knowledge_root)
    issue_codes = {issue.code for issue in report.issues}

    assert report.passed is False
    assert report.error_count >= 3
    assert report.metrics["empty_documents"] == 1
    assert report.metrics["broken_asset_references"] == 1
    assert report.metrics["invalid_chunk_groups"] == 1
    assert {"empty_searchable_body", "broken_asset_uri", "invalid_chunk_group"} <= issue_codes


def test_background_build_job_persists_progress_and_result(knowledge_root: Path) -> None:
    source = knowledge_root / "通用资料" / "设备说明.md"
    source.parent.mkdir(parents=True)
    source.write_text("# 设备说明\n\n## 工作原理\n\n" + "设备通过双阶段校验完成数据采集。" * 10, encoding="utf-8")
    manager = KnowledgeBuildJobManager(max_workers=1)

    submitted = manager.submit(KnowledgeIndexBuildRequest(folder_path="通用资料"), user_id="alice")
    completed = manager.wait(submitted.job_id, user_id="alice")
    reloaded = KnowledgeBuildJobManager(max_workers=1).get(submitted.job_id, user_id="alice")

    assert completed.state in {"completed", "completed_with_warnings"}
    assert completed.progress.percent == 100.0
    assert completed.result is not None
    assert completed.result.quality_report is not None
    assert completed.result.entries == []
    assert reloaded.state == completed.state
    assert reloaded.result is not None


def test_background_build_rejects_concurrent_job_for_same_root(
    knowledge_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_root.mkdir()
    started = threading.Event()
    release = threading.Event()

    def blocking_build(*_args, **_kwargs) -> KnowledgeIndexBuildResponse:
        started.set()
        assert release.wait(timeout=5)
        return KnowledgeIndexBuildResponse(
            root_path=str(knowledge_root),
            scanned_files=0,
            created=0,
            updated=0,
            skipped=0,
        )

    monkeypatch.setattr("deerflow.knowledge.build_jobs.build_knowledge_index_from_folder", blocking_build)
    manager = KnowledgeBuildJobManager(max_workers=1)
    first = manager.submit(KnowledgeIndexBuildRequest(), user_id="alice")
    assert started.wait(timeout=5)

    with pytest.raises(KnowledgeBuildJobConflictError):
        manager.submit(KnowledgeIndexBuildRequest(), user_id="alice")

    release.set()
    assert manager.wait(first.job_id, user_id="alice").state == "completed"


def test_background_build_records_failures(
    knowledge_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge_root.mkdir()

    def failed_build(*_args, **_kwargs):
        raise RuntimeError("embedding service unavailable")

    monkeypatch.setattr("deerflow.knowledge.build_jobs.build_knowledge_index_from_folder", failed_build)
    manager = KnowledgeBuildJobManager(max_workers=1)
    submitted = manager.submit(KnowledgeIndexBuildRequest(), user_id="alice")
    failed = manager.wait(submitted.job_id, user_id="alice")

    assert failed.state == "failed"
    assert failed.progress.stage == "failed"
    assert failed.error == "embedding service unavailable"


def test_background_build_api_returns_accepted_job_and_pollable_result(knowledge_root: Path) -> None:
    source = knowledge_root / "通用资料" / "API资料.md"
    source.parent.mkdir(parents=True)
    source.write_text("# API 资料\n\n## 正文\n\n后台构建任务测试正文。" * 5, encoding="utf-8")
    app = FastAPI()
    app.include_router(knowledge_router.router)

    with TestClient(app) as client:
        started = client.post(
            "/api/knowledge/index/build-jobs",
            json={"folder_path": "通用资料"},
        )
        assert started.status_code == 202
        job_id = started.json()["job_id"]

        status = None
        for _ in range(100):
            status = client.get(f"/api/knowledge/index/build-jobs/{job_id}")
            assert status.status_code == 200
            if status.json()["state"] in {"completed", "completed_with_warnings", "failed"}:
                break
            sleep(0.02)

    assert status is not None
    assert status.json()["state"] in {"completed", "completed_with_warnings"}
    assert status.json()["progress"]["percent"] == 100.0
    assert status.json()["result"]["quality_report"]["passed"] is True
