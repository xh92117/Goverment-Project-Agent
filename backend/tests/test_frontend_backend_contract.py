"""Frontend-facing Gateway contract smoke tests."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_frontend_thread_workflow_contract(monkeypatch, tmp_path):
    """Exercise the HTTP endpoints used by the chat page against the real app."""
    monkeypatch.setenv("GATEWAY_ENABLE_LOCAL_AUTH", "false")
    monkeypatch.setenv("AGENT_BASE_AUTH_DISABLED", "1")
    runtime_home = tmp_path / "runtime"
    data_dir = runtime_home / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("AGENT_BASE_HOME", str(runtime_home))
    monkeypatch.setenv("AGENT_BASE_DB_PATH", str(data_dir / "agent_base.db"))

    import app.gateway.config as gateway_config
    import deerflow.config.app_config as app_config
    import deerflow.config.paths as paths_config

    monkeypatch.setattr(gateway_config, "_gateway_config", None)
    monkeypatch.setattr(app_config, "_app_config", None)
    monkeypatch.setattr(app_config, "_app_config_is_custom", False)
    monkeypatch.setattr(paths_config, "_paths", None)

    from app.gateway.app import create_app

    thread_id = f"contract-{uuid.uuid4()}"
    app = create_app()

    with TestClient(app) as client:
        models = client.get("/api/models")
        assert models.status_code == 200, models.text
        assert "models" in models.json()

        created = client.post(
            "/api/threads",
            json={
                "thread_id": thread_id,
                "assistant_id": "lead_agent",
                "metadata": {"title": "contract smoke"},
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["thread_id"] == thread_id

        searched = client.post("/api/threads/search", json={"limit": 10, "offset": 0, "metadata": {}})
        assert searched.status_code == 200, searched.text
        assert any(item["thread_id"] == thread_id for item in searched.json())

        messages = client.get(f"/api/threads/{thread_id}/messages")
        assert messages.status_code == 200, messages.text
        assert isinstance(messages.json(), list)

        deleted = client.delete(f"/api/threads/{thread_id}")
        assert deleted.status_code == 200, deleted.text
