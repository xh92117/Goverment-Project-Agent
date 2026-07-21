import zipfile
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gateway.routers import projects
from deerflow.config.paths import Paths
from deerflow.knowledge.export_images import ExportEvidenceEnrichment, NoVerifiedImageEvidenceError


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(projects, "get_paths", lambda: Paths(tmp_path))
    app = FastAPI()
    app.include_router(projects.router)
    return TestClient(app)


def _docx_document_xml(data: bytes) -> str:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def test_create_and_list_projects(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        created = client.post("/api/projects", json={"name": "2026 面上项目"})
        listed = client.get("/api/projects")

    assert created.status_code == 200, created.text
    body = created.json()
    assert body["name"] == "2026 面上项目"
    assert body["root_path"].endswith(body["project_id"])
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["project_id"] == body["project_id"]


def test_project_directory_controls_project_file_root(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "government_project_workspace_root", lambda: tmp_path / "workspace")
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "自定义目录项目"}).json()
        project_id = project["project_id"]
        custom_root = tmp_path / "selected-project-dir"

        directory = client.put(
            f"/api/projects/{project_id}/directory",
            json={"root_path": str(custom_root), "create": True},
        )
        written = client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/result.md", "content": "# Result"},
        )
        uploaded = client.post(
            f"/api/projects/{project_id}/files/upload",
            params={"category": "inputs"},
            files=[("files", ("guide.txt", b"guide", "text/plain"))],
        )
        fetched = client.get(f"/api/projects/{project_id}")

    assert directory.status_code == 200, directory.text
    assert directory.json()["root_path"] == str(custom_root.resolve())
    assert directory.json()["default_root_path"] == str((tmp_path / "workspace").resolve())
    assert written.status_code == 200, written.text
    assert uploaded.status_code == 200, uploaded.text
    assert fetched.json()["root_path"] == str(custom_root.resolve())
    assert (custom_root / "outputs" / "result.md").read_text(encoding="utf-8") == "# Result"
    assert (custom_root / "inputs" / "guide.txt").read_text(encoding="utf-8") == "guide"
    assert not (tmp_path / "projects" / project_id / "outputs" / "result.md").exists()


def test_project_directory_select_returns_chosen_path(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "government_project_workspace_root", lambda: tmp_path / "workspace")
    selected_root = tmp_path / "picked-project-dir"
    selected_root.mkdir()
    monkeypatch.setattr(projects, "_select_project_directory", lambda initial_dir: selected_root)

    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "选择目录项目"}).json()
        selected = client.post(f"/api/projects/{project['project_id']}/directory/select")

    assert selected.status_code == 200, selected.text
    body = selected.json()
    assert body["selected"] is True
    assert body["project_id"] == project["project_id"]
    assert body["root_path"] == str(selected_root.resolve())


def test_project_directory_select_supports_cancel(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "_select_project_directory", lambda initial_dir: None)

    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "取消选择目录项目"}).json()
        selected = client.post(f"/api/projects/{project['project_id']}/directory/select")

    assert selected.status_code == 200, selected.text
    assert selected.json() == {"project_id": project["project_id"], "root_path": None, "selected": False}


def test_project_draft_roundtrip_and_file_tree(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "申报项目"}).json()
        project_id = project["project_id"]
        saved = client.put(
            f"/api/projects/{project_id}/drafts/研究方案/技术路线",
            json={"content": "# 技术路线\n\n内容"},
        )
        read = client.get(f"/api/projects/{project_id}/drafts/研究方案/技术路线")
        files = client.get(f"/api/projects/{project_id}/files")

    assert saved.status_code == 200, saved.text
    assert saved.json()["section_name"] == "研究方案/技术路线"
    assert read.status_code == 200, read.text
    assert read.json()["content"].startswith("# 技术路线")
    assert files.status_code == 200, files.text
    assert any(item["path"] == "drafts/研究方案/技术路线.md" for item in files.json()["files"])


def test_project_draft_versions_roundtrip(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "申报项目"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/drafts/研究方案/技术路线",
            json={"content": "v1"},
        )
        created = client.post(f"/api/projects/{project_id}/draft-versions/研究方案/技术路线")
        version_id = created.json()["version"]["version_id"]
        client.put(
            f"/api/projects/{project_id}/drafts/研究方案/技术路线",
            json={"content": "v2"},
        )
        listed = client.get(f"/api/projects/{project_id}/draft-versions/研究方案/技术路线")
        read = client.get(
            f"/api/projects/{project_id}/draft-version-content/研究方案/技术路线",
            params={"version_id": version_id},
        )
        files = client.get(f"/api/projects/{project_id}/files")

    assert created.status_code == 200, created.text
    assert listed.status_code == 200, listed.text
    assert listed.json()["versions"][0]["version_id"] == version_id
    assert read.status_code == 200, read.text
    assert read.json()["content"] == "v1"
    assert any(item["category"] == "version" for item in files.json()["files"])


def test_project_owner_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(projects, "get_effective_user_id", lambda: "owner-a")
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "私有项目"}).json()
        project_id = project["project_id"]

        monkeypatch.setattr(projects, "get_effective_user_id", lambda: "owner-b")
        listed = client.get("/api/projects")
        fetched = client.get(f"/api/projects/{project_id}")

    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    assert fetched.status_code == 404


def test_same_project_id_uses_distinct_physical_user_roots(tmp_path, monkeypatch):
    """Project IDs are tenant-local and must not collide on disk."""
    current_user = {"id": "owner-a"}
    monkeypatch.setattr(projects, "get_effective_user_id", lambda: current_user["id"])

    with _client(tmp_path, monkeypatch) as client:
        first = client.post(
            "/api/projects",
            json={"project_id": "shared-name", "name": "A project"},
        )
        current_user["id"] = "owner-b"
        second = client.post(
            "/api/projects",
            json={"project_id": "shared-name", "name": "B project"},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["root_path"] != second.json()["root_path"]


def test_project_file_upload_summary_download_and_delete(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "Upload Project"}).json()
        project_id = project["project_id"]
        upload = client.post(
            f"/api/projects/{project_id}/files/upload",
            params={"category": "inputs"},
            files=[("files", ("guide.txt", b"hello project", "text/plain"))],
        )
        summary = client.get(f"/api/projects/{project_id}/summary")
        download = client.get(
            f"/api/projects/{project_id}/files/download",
            params={"path": "inputs/guide.txt"},
        )
        deleted = client.delete(
            f"/api/projects/{project_id}/files",
            params={"path": "inputs/guide.txt"},
        )
        files = client.get(f"/api/projects/{project_id}/files")

    assert upload.status_code == 200, upload.text
    assert upload.json()["files"][0]["path"] == "inputs/guide.txt"
    assert summary.status_code == 200, summary.text
    assert summary.json()["inputs_count"] == 1
    assert summary.json()["files_count"] == 1
    assert download.status_code == 200, download.text
    assert download.content == b"hello project"
    assert deleted.status_code == 204, deleted.text
    assert not files.json()["files"]


def test_project_file_write_supports_project_and_thread_sources(tmp_path, monkeypatch):
    class FakePaths(Paths):
        def sandbox_outputs_dir(self, thread_id, user_id=None):
            return tmp_path / "thread-outputs" / thread_id

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(projects, "get_paths", lambda: FakePaths(tmp_path))
    with client:
        project = client.post("/api/projects", json={"name": "Writable Project"}).json()
        project_id = project["project_id"]
        project_write = client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/project-note.md", "content": "# Project"},
        )
        thread_write = client.put(
            f"/api/projects/{project_id}/files/write",
            json={
                "path": "thread-note.md",
                "source": "thread",
                "thread_id": "thread-1",
                "content": "# Thread",
            },
        )

    assert project_write.status_code == 200, project_write.text
    assert project_write.json()["path"] == "outputs/project-note.md"
    assert thread_write.status_code == 200, thread_write.text
    assert thread_write.json()["source"] == "thread"
    assert thread_write.json()["thread_id"] == "thread-1"
    assert (tmp_path / "thread-outputs" / "thread-1" / "thread-note.md").read_text(encoding="utf-8") == "# Thread"


def test_project_file_delete_supports_thread_sources(tmp_path, monkeypatch):
    class FakePaths(Paths):
        def sandbox_outputs_dir(self, thread_id, user_id=None):
            return tmp_path / "thread-outputs" / thread_id

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(projects, "get_paths", lambda: FakePaths(tmp_path))
    with client:
        project = client.post("/api/projects", json={"name": "Thread Delete Project"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={
                "path": "thread-note.md",
                "source": "thread",
                "thread_id": "thread-1",
                "content": "# Thread",
            },
        )
        deleted = client.delete(
            f"/api/projects/{project_id}/files",
            params={"path": "thread-note.md", "source": "thread", "thread_id": "thread-1"},
        )

    assert deleted.status_code == 204, deleted.text
    assert not (tmp_path / "thread-outputs" / "thread-1" / "thread-note.md").exists()


def test_project_file_tree_hides_project_draft_artifact_mirrors(tmp_path, monkeypatch):
    class FakePaths(Paths):
        def sandbox_outputs_dir(self, thread_id, user_id=None):
            return tmp_path / "thread-outputs" / thread_id

    async def fake_project_threads(project_id, request):
        return [{"thread_id": "thread-1"}]

    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(projects, "get_paths", lambda: FakePaths(tmp_path))
    monkeypatch.setattr(projects, "_project_threads", fake_project_threads)
    with client:
        project = client.post("/api/projects", json={"name": "Dedup Project"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "drafts/国内外研究现状.md", "content": "# Draft"},
        )
        outputs_root = tmp_path / "thread-outputs" / "thread-1"
        (outputs_root / "projects" / project_id / "drafts").mkdir(parents=True)
        (outputs_root / "projects" / project_id / "drafts" / "国内外研究现状.md").write_text("# Draft", encoding="utf-8")
        (outputs_root / "reports").mkdir(parents=True)
        (outputs_root / "reports" / "运行报告.md").write_text("# Report", encoding="utf-8")
        files = client.get(f"/api/projects/{project_id}/files")

    assert files.status_code == 200, files.text
    listed = files.json()["files"]
    assert any(item["id"] == "project:drafts/国内外研究现状.md" for item in listed)
    assert any(item["id"] == "thread:thread-1:reports/运行报告.md" for item in listed)
    assert not any(item["id"] == f"thread:thread-1:projects/{project_id}/drafts/国内外研究现状.md" for item in listed)


def test_project_file_export_docx_merged_and_separate(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "Export Project"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/研究方案与技术路线.md", "content": "# 技术路线\n\nA"},
        )
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/项目背景与立项目的.md", "content": "# 背景\n\nB"},
        )
        payload = {
            "files": [
                {"path": "outputs/研究方案与技术路线.md", "name": "研究方案与技术路线.md"},
                {"path": "outputs/项目背景与立项目的.md", "name": "项目背景与立项目的.md"},
            ],
            "title": "Export Project",
        }
        merged = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={**payload, "mode": "merged"},
        )
        separate = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={**payload, "mode": "separate"},
        )

    assert merged.status_code == 200, merged.text
    assert merged.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert merged.content.startswith(b"PK")
    assert separate.status_code == 200, separate.text
    assert separate.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(BytesIO(separate.content)) as archive:
        names = archive.namelist()
    assert len(names) == 2
    assert all(name.endswith(".docx") for name in names)


def test_project_file_export_docx_renders_markdown_and_deduplicates_headings(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "Global Project"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={
                "path": "outputs/background.md",
                "content": ("# Global Project\n\n## Background\n\n#### 1. Need\n\n- First **bold** item\n- Second item\n\nRange 10~100 and formula $D_{index}$.\n\n| Item | Description |\n| --- | --- |\n| A | Long table value |\n"),
            },
        )
        response = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={
                "files": [{"path": "outputs/background.md", "name": "Background.md"}],
                "mode": "merged",
                "title": "Global Project",
            },
        )

    assert response.status_code == 200, response.text
    document_xml = _docx_document_xml(response.content)
    assert document_xml.count("Global Project") == 1
    assert document_xml.count("Background") == 1
    assert "####" not in document_xml
    assert "- First" not in document_xml
    assert '<w:pStyle w:val="Heading4"/>' in document_xml
    assert '<w:numId w:val="2"/>' in document_xml
    assert "<w:b/><w:bCs/>" in document_xml
    assert "10~100" in document_xml
    assert "<m:sSub>" in document_xml
    assert "index" in document_xml
    assert "浠垮畫" not in document_xml
    assert '<w:tblW w:w="9360" w:type="dxa"/>' in document_xml
    assert "<w:tcMar>" in document_xml
    assert '<w:shd w:fill="F4F6F9"/>' in document_xml


def test_project_file_export_with_images_runs_agent_before_building_docx(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_enrich(documents, *, applicant_id, model_name, user_id):
        captured["documents"] = documents
        captured["applicant_id"] = applicant_id
        captured["model_name"] = model_name
        captured["user_id"] = user_id
        return ExportEvidenceEnrichment(
            markdowns=[f"{documents[0].content}\n\n![License](evidence://default/evd_verified)"],
            evidence_count=1,
            model_name=model_name or "default-model",
        )

    def fake_build(title, markdown, **kwargs):
        captured["markdown"] = markdown
        return b"PK-export"

    monkeypatch.setattr(projects, "enrich_export_documents_with_images", fake_enrich)
    monkeypatch.setattr(projects, "build_markdown_docx", fake_build)

    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "Image Export"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/foundation.md", "content": "# Foundation\n\nApplicant qualification."},
        )
        response = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={
                "files": [{"path": "outputs/foundation.md", "name": "foundation.md"}],
                "mode": "merged",
                "include_images": True,
                "applicant_id": "default",
                "model_name": "qwen-selector",
            },
        )

    assert response.status_code == 200, response.text
    assert response.headers["x-embedded-evidence-count"] == "1"
    assert captured["applicant_id"] == "default"
    assert captured["model_name"] == "qwen-selector"
    assert "evidence://default/evd_verified" in captured["markdown"]


def test_project_file_export_without_images_keeps_direct_path(tmp_path, monkeypatch):
    async def unexpected_enrich(*args, **kwargs):
        pytest.fail("direct export must not run the image-selection agent")

    monkeypatch.setattr(projects, "enrich_export_documents_with_images", unexpected_enrich)

    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "Direct Export"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/direct.md", "content": "# Direct export"},
        )
        response = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={
                "files": [{"path": "outputs/direct.md", "name": "direct.md"}],
                "mode": "merged",
                "include_images": False,
            },
        )

    assert response.status_code == 200, response.text
    assert response.headers["x-embedded-evidence-count"] == "0"


def test_project_file_export_with_images_reports_missing_verified_evidence(tmp_path, monkeypatch):
    async def missing_evidence(*args, **kwargs):
        raise NoVerifiedImageEvidenceError

    monkeypatch.setattr(projects, "enrich_export_documents_with_images", missing_evidence)

    with _client(tmp_path, monkeypatch) as client:
        project = client.post("/api/projects", json={"name": "No Evidence"}).json()
        project_id = project["project_id"]
        client.put(
            f"/api/projects/{project_id}/files/write",
            json={"path": "outputs/foundation.md", "content": "# Foundation"},
        )
        response = client.post(
            f"/api/projects/{project_id}/files/export-docx",
            json={
                "files": [{"path": "outputs/foundation.md", "name": "foundation.md"}],
                "mode": "merged",
                "include_images": True,
            },
        )

    assert response.status_code == 409
    assert "人工确认" in response.json()["detail"]
