"""Tenant isolation tests for proposal draft storage."""

from types import SimpleNamespace

from deerflow.config.paths import Paths


def test_proposal_drafts_root_is_user_scoped(tmp_path, monkeypatch):
    from app.gateway.routers import proposal_drafts

    current_user = {"id": "user-a"}
    monkeypatch.setattr(proposal_drafts, "get_paths", lambda: Paths(tmp_path), raising=False)
    monkeypatch.setattr(
        proposal_drafts,
        "get_effective_user_id",
        lambda: current_user["id"],
        raising=False,
    )

    first = proposal_drafts._drafts_root()
    current_user["id"] = "user-b"
    second = proposal_drafts._drafts_root()

    assert first == tmp_path / "users" / "user-a" / "proposal_drafts"
    assert second == tmp_path / "users" / "user-b" / "proposal_drafts"
    assert first != second


def test_proposal_tool_roots_follow_runtime_user(tmp_path, monkeypatch):
    from deerflow.tools.builtins import proposal_workspace_tool

    monkeypatch.setattr(proposal_workspace_tool, "get_paths", lambda: Paths(tmp_path), raising=False)
    runtime_a = SimpleNamespace(context={"user_id": "user-a"})
    runtime_b = SimpleNamespace(context={"user_id": "user-b"})

    assert proposal_workspace_tool._proposal_workspace_root(runtime_a) == (
        tmp_path / "users" / "user-a" / "proposal_drafts"
    )
    assert proposal_workspace_tool._proposal_workspace_root(runtime_b) == (
        tmp_path / "users" / "user-b" / "proposal_drafts"
    )
    assert proposal_workspace_tool._project_meta_dir("project-1", runtime_a) == (
        tmp_path / "users" / "user-a" / "projects" / "project-1"
    )


def test_proposal_tool_rejects_tampered_external_project_root(tmp_path, monkeypatch):
    import json

    from deerflow.tools.builtins import proposal_workspace_tool

    monkeypatch.setenv("AGENT_BASE_STRICT_USER_CONTEXT", "true")
    monkeypatch.setattr(proposal_workspace_tool, "get_paths", lambda: Paths(tmp_path))
    runtime = SimpleNamespace(
        context={"user_id": "user-a", "project_id": "project-1"},
        state={"thread_data": {}},
    )
    meta_dir = tmp_path / "users" / "user-a" / "projects" / "project-1"
    outside = tmp_path / "outside-user-root"
    meta_dir.mkdir(parents=True)
    (meta_dir / ".project.json").write_text(
        json.dumps({"root_path": str(outside)}),
        encoding="utf-8",
    )

    proposal_workspace_tool.proposal_save_markdown_tool.func(
        runtime=runtime,
        task_name="project",
        section_name="section",
        content="private",
        tool_call_id="call-1",
    )

    assert not (outside / "drafts" / "section.md").exists()
    assert (meta_dir / "drafts" / "section.md").read_text(encoding="utf-8") == "private"
