"""Public/private knowledge-base isolation and retrieval tests."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from deerflow.config.paths import Paths
from deerflow.knowledge import KnowledgeFileReadRequest, KnowledgeIndexEntryCreate, KnowledgeIndexSearchRequest
from deerflow.knowledge import storage as knowledge_storage


def _entry(title: str, file_path: str) -> KnowledgeIndexEntryCreate:
    return KnowledgeIndexEntryCreate(
        title=title,
        category="test",
        file_path=file_path,
        summary=title,
    )


def _configure_roots(tmp_path: Path, monkeypatch) -> Path:
    public_root = tmp_path / "public-knowledge"
    public_root.mkdir()
    monkeypatch.setattr(
        knowledge_storage,
        "government_project_knowledge_root",
        lambda: public_root,
    )
    monkeypatch.setattr(knowledge_storage, "get_paths", lambda: Paths(tmp_path / "state"))
    monkeypatch.setattr(
        knowledge_storage,
        "_storage_instance",
        knowledge_storage.FileKnowledgeBaseStorage(),
    )
    return public_root


def test_public_and_private_knowledge_roots_are_distinct(tmp_path, monkeypatch):
    public_root = _configure_roots(tmp_path, monkeypatch)

    assert knowledge_storage._knowledge_root_path() == public_root
    assert knowledge_storage._knowledge_root_path(user_id="user-a") == (
        tmp_path / "state" / "users" / "user-a" / "knowledge_base"
    )
    assert knowledge_storage._knowledge_root_path(user_id="user-b") != (
        knowledge_storage._knowledge_root_path(user_id="user-a")
    )


def test_combined_search_returns_public_plus_callers_private_only(tmp_path, monkeypatch):
    _configure_roots(tmp_path, monkeypatch)
    knowledge_storage.create_knowledge_index_entry(_entry("public guide", "public.md"), user_id=None)
    knowledge_storage.create_knowledge_index_entry(_entry("alice evidence", "alice.md"), user_id="alice")

    alice = knowledge_storage.search_knowledge_index_entries_combined(
        KnowledgeIndexSearchRequest(query="", limit=10),
        user_id="alice",
    )
    bob = knowledge_storage.search_knowledge_index_entries_combined(
        KnowledgeIndexSearchRequest(query="", limit=10),
        user_id="bob",
    )

    assert {result.entry.title for result in alice.results} == {"public guide", "alice evidence"}
    assert {result.scope for result in alice.results} == {"public", "private"}
    assert [result.entry.title for result in bob.results] == ["public guide"]
    assert bob.results[0].scope == "public"


def test_combined_read_resolves_scope_and_prefers_private(tmp_path, monkeypatch):
    public_root = _configure_roots(tmp_path, monkeypatch)
    private_root = knowledge_storage._knowledge_root_path(user_id="alice")
    public_root.joinpath("same.md").write_text("public", encoding="utf-8")
    private_root.mkdir(parents=True)
    private_root.joinpath("same.md").write_text("private", encoding="utf-8")

    automatic = knowledge_storage.read_knowledge_file_combined(
        KnowledgeFileReadRequest(file_path="same.md"),
        user_id="alice",
    )
    public = knowledge_storage.read_knowledge_file_combined(
        KnowledgeFileReadRequest(file_path="same.md"),
        user_id="alice",
        scope="public",
    )

    assert automatic.content == "private"
    assert automatic.scope == "private"
    assert public.content == "public"
    assert public.scope == "public"


def test_agent_tools_search_and_read_across_public_and_private(tmp_path, monkeypatch):
    from deerflow.tools.builtins import knowledge_tools

    public_root = _configure_roots(tmp_path, monkeypatch)
    knowledge_storage.create_knowledge_index_entry(_entry("public guide", "public.md"), user_id=None)
    knowledge_storage.create_knowledge_index_entry(_entry("alice evidence", "alice.md"), user_id="alice")
    public_root.joinpath("public.md").write_text("shared policy", encoding="utf-8")
    monkeypatch.setattr(knowledge_tools, "get_effective_user_id", lambda: "alice")

    search_text = knowledge_tools.knowledge_search_index_tool.func(query="", limit=10)
    read_text = knowledge_tools.knowledge_read_file_tool.func(file_path="public.md")

    assert "public guide" in search_text
    assert "alice evidence" in search_text
    assert "knowledge_scope: public" in search_text
    assert "shared policy" in read_text
    assert "knowledge_scope: public" in read_text


def test_knowledge_api_searches_and_reads_combined_scope(tmp_path, monkeypatch):
    from app.gateway.routers import knowledge

    public_root = _configure_roots(tmp_path, monkeypatch)
    knowledge_storage.create_knowledge_index_entry(_entry("public guide", "public.md"), user_id=None)
    knowledge_storage.create_knowledge_index_entry(_entry("alice evidence", "alice.md"), user_id="alice")
    public_root.joinpath("public.md").write_text("shared policy", encoding="utf-8")
    monkeypatch.setattr(knowledge, "get_effective_user_id", lambda: "alice")
    app = FastAPI()
    app.include_router(knowledge.router)

    with TestClient(app) as client:
        searched = client.post("/api/knowledge/index/search", json={"query": "", "limit": 10})
        read = client.post("/api/knowledge/files/read", json={"file_path": "public.md"})

    assert searched.status_code == 200, searched.text
    assert {item["entry"]["title"] for item in searched.json()["results"]} == {
        "public guide",
        "alice evidence",
    }
    assert read.status_code == 200, read.text
    assert read.json()["scope"] == "public"


def test_non_admin_cannot_create_public_knowledge_entry(tmp_path, monkeypatch):
    from app.gateway.routers import knowledge

    _configure_roots(tmp_path, monkeypatch)
    app = FastAPI()

    class UserMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = type("User", (), {"id": "alice", "system_role": "user"})()
            return await call_next(request)

    app.add_middleware(UserMiddleware)
    app.include_router(knowledge.router)
    with TestClient(app) as client:
        response = client.post(
            "/api/knowledge/index?scope=public",
            json={"title": "shared", "category": "test", "file_path": "shared.md"},
        )

    assert response.status_code == 403
    assert knowledge_storage.list_knowledge_index_entries(user_id=None) == []


def test_admin_scope_query_targets_public_crud(tmp_path, monkeypatch):
    from app.gateway.routers import knowledge

    public_root = _configure_roots(tmp_path, monkeypatch)
    monkeypatch.setattr(knowledge, "get_effective_user_id", lambda: "alice")
    app = FastAPI()

    class AdminMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user = type("User", (), {"id": "admin", "system_role": "admin"})()
            return await call_next(request)

    app.add_middleware(AdminMiddleware)
    app.include_router(knowledge.router)
    public_root.joinpath("editable.md").write_text("old", encoding="utf-8")
    with TestClient(app) as client:
        created = client.post(
            "/api/knowledge/documents?scope=public",
            json={
                "title": "shared doc",
                "library": "policy_guides",
                "doc_type": "guide",
                "content": "shared",
            },
        )
        public_list = client.get("/api/knowledge/documents?scope=public")
        private_list = client.get("/api/knowledge/documents?scope=private")
        saved = client.put(
            "/api/knowledge/files/save?scope=public",
            json={"file_path": "editable.md", "content": "new"},
        )

    assert created.status_code == 200, created.text
    assert [item["title"] for item in public_list.json()] == ["shared doc"]
    assert private_list.json() == []
    assert saved.status_code == 200, saved.text
    assert public_root.joinpath("editable.md").read_text(encoding="utf-8") == "new"
