from types import SimpleNamespace

import anyio
import pytest
import yaml
from fastapi import HTTPException

from app.gateway.routers import settings as settings_router
from deerflow import government_project_workspace as gp_workspace


def _admin_request():
    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(system_role="admin")))


def _runtime_path_update(root):
    workspace = root / "workspace"
    return settings_router.RuntimePathSettingsUpdate(
        gp_agent_home=str(root),
        runtime_home=str(root / ".agent-base"),
        workspace_root=str(workspace),
        knowledge_root=str(workspace / "knowledge_base"),
        drafts_root=str(workspace / "proposal_drafts"),
        projects_root=str(workspace / "projects"),
        logs_root=str(root / "logs"),
    )


def test_get_runtime_path_settings_reads_env_and_derives_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models: []\n", encoding="utf-8")
    root = tmp_path / "configured-gp-agent"
    (tmp_path / ".env").write_text(f'GP_AGENT_HOME="{root}"\n', encoding="utf-8")
    monkeypatch.setattr(settings_router.AppConfig, "resolve_config_path", staticmethod(lambda: config_path))

    result = anyio.run(settings_router.get_runtime_path_settings, _admin_request())

    assert result.gp_agent_home == str(root)
    assert result.runtime_home == str(root / ".agent-base")
    assert result.workspace_root == str(root / "workspace")
    assert result.knowledge_root == str(root / "workspace" / "knowledge_base")
    assert result.restart_required is False


def test_update_runtime_path_settings_writes_related_env_values(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models: []\n", encoding="utf-8")
    monkeypatch.setattr(settings_router.AppConfig, "resolve_config_path", staticmethod(lambda: config_path))
    root = tmp_path / "new-gp-agent"

    result = anyio.run(
        settings_router.update_runtime_path_settings,
        _admin_request(),
        _runtime_path_update(root),
    )

    env_values = settings_router.read_env_file(tmp_path / ".env")
    assert env_values["GP_AGENT_HOME"] == str(root)
    assert env_values["AGENT_BASE_HOME"] == str(root / ".agent-base")
    assert env_values["AGENT_BASE_HOST_BASE_DIR"] == str(root / ".agent-base")
    assert env_values["GOVERNMENT_PROJECT_WORKSPACE_ROOT"] == str(root / "workspace")
    assert env_values["AGENT_BASE_KNOWLEDGE_ROOT"] == str(root / "workspace" / "knowledge_base")
    assert env_values["GOVERNMENT_PROJECT_DRAFTS_ROOT"] == str(root / "workspace" / "proposal_drafts")
    assert env_values["GOVERNMENT_PROJECT_PROJECTS_ROOT"] == str(root / "workspace" / "projects")
    assert env_values["GOVERNMENT_PROJECT_LOG_ROOT"] == str(root / "logs")
    assert env_values["AGENT_BASE_DB_PATH"] == str(root / ".agent-base" / "data" / "agent_base.db")
    assert result.restart_required is True


def test_update_runtime_path_settings_rejects_source_tree(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models: []\n", encoding="utf-8")
    monkeypatch.setattr(settings_router.AppConfig, "resolve_config_path", staticmethod(lambda: config_path))
    source_path = gp_workspace.repo_root() / "runtime-data"

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(
            settings_router.update_runtime_path_settings,
            _admin_request(),
            _runtime_path_update(source_path),
        )

    assert exc_info.value.status_code == 400
    assert "outside the source-code tree" in str(exc_info.value.detail)


def test_get_pdf_parser_settings_masks_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
uploads:
  pdf_converter: markitdown
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MINERU_API_TOKEN=real-token",
                "MINERU_API_BASE_URL=https://mineru.example",
                "MINERU_MODEL_VERSION=vlm",
                "MINERU_LANGUAGE=ch",
                "MINERU_TIMEOUT_SECONDS=30",
                "MINERU_POLL_INTERVAL_SECONDS=3",
                "MINERU_MAX_WAIT_SECONDS=600",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    result = anyio.run(settings_router.get_pdf_parser_settings, _admin_request())

    assert result.api_token == "***"
    assert result.token_configured is True
    assert result.api_base_url == "https://mineru.example"
    assert result.timeout_seconds == 30
    assert result.pdf_converter == "markitdown"


def test_update_pdf_parser_settings_writes_env_and_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models: []\n", encoding="utf-8")
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )
    monkeypatch.setattr(settings_router, "reload_app_config", lambda path: SimpleNamespace())
    monkeypatch.delenv("MINERU_API_TOKEN", raising=False)

    body = settings_router.PdfParserSettingsUpdate(
        api_token="new-token",
        api_base_url="https://mineru.example/",
        model_version="vlm",
        language="ch",
        timeout_seconds=45,
        poll_interval_seconds=4,
        max_wait_seconds=1200,
        pdf_converter="pymupdf4llm",
    )
    result = anyio.run(settings_router.update_pdf_parser_settings, _admin_request(), body)

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "MINERU_API_TOKEN=new-token" in env_text
    assert "MINERU_API_BASE_URL=https://mineru.example" in env_text
    assert saved["uploads"]["pdf_converter"] == "pymupdf4llm"
    assert result.api_token == "***"
    assert result.token_configured is True
    assert result.max_wait_seconds == 1200
    assert settings_router.os.environ["MINERU_API_TOKEN"] == "new-token"


def test_update_pdf_parser_settings_preserves_masked_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
uploads:
  pdf_converter: auto
""",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("MINERU_API_TOKEN=existing-token\n", encoding="utf-8")
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )
    monkeypatch.setattr(settings_router, "reload_app_config", lambda path: SimpleNamespace())

    body = settings_router.PdfParserSettingsUpdate(
        api_token="***",
        api_base_url="https://mineru.net",
        model_version="vlm",
        language="ch",
        timeout_seconds=60,
        poll_interval_seconds=5,
        max_wait_seconds=900,
        pdf_converter="auto",
    )
    anyio.run(settings_router.update_pdf_parser_settings, _admin_request(), body)

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MINERU_API_TOKEN=existing-token" in env_text
    assert settings_router.os.environ["MINERU_API_TOKEN"] == "existing-token"


def test_update_pdf_parser_settings_clears_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("models: []\n", encoding="utf-8")
    (tmp_path / ".env").write_text("MINERU_API_TOKEN=existing-token\n", encoding="utf-8")
    monkeypatch.setenv("MINERU_API_TOKEN", "existing-token")
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )
    monkeypatch.setattr(settings_router, "reload_app_config", lambda path: SimpleNamespace())

    body = settings_router.PdfParserSettingsUpdate(
        clear_token=True,
        api_base_url="https://mineru.net",
        model_version="vlm",
        language="ch",
        timeout_seconds=60,
        poll_interval_seconds=5,
        max_wait_seconds=900,
        pdf_converter="auto",
    )
    result = anyio.run(settings_router.update_pdf_parser_settings, _admin_request(), body)

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MINERU_API_TOKEN" not in env_text
    assert "MINERU_API_TOKEN" not in settings_router.os.environ
    assert result.token_configured is False


def test_get_knowledge_image_model_settings_lists_only_vision_models(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
knowledge_image_model: text-only
models:
  - name: text-only
    model: deepseek-chat
    provider: deepseek
    supports_vision: false
  - name: qwen-vl
    model: qwen-vl-max
    provider: qwen
    display_name: 通义千问视觉
    supports_vision: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    result = anyio.run(settings_router.get_knowledge_image_model_settings, _admin_request())

    assert result.selected_model == "text-only"
    assert result.selected_model_valid is False
    assert [model.name for model in result.vision_models] == ["qwen-vl"]
    assert result.vision_models[0].display_name == "通义千问视觉"


def test_update_knowledge_image_model_settings_persists_valid_model(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
knowledge_image_model: null
models:
  - name: qwen-vl
    model: qwen-vl-max
    provider: qwen
    supports_vision: true
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )
    reloaded_paths: list[str] = []
    monkeypatch.setattr(settings_router, "reload_app_config", reloaded_paths.append)

    result = anyio.run(
        settings_router.update_knowledge_image_model_settings,
        _admin_request(),
        settings_router.KnowledgeImageModelSettingsUpdate(model_name="qwen-vl"),
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["knowledge_image_model"] == "qwen-vl"
    assert result.selected_model == "qwen-vl"
    assert result.selected_model_valid is True
    assert reloaded_paths == [str(config_path)]


def test_update_knowledge_image_model_settings_rejects_non_vision_model(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: text-only
    model: deepseek-chat
    supports_vision: false
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        settings_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(
            settings_router.update_knowledge_image_model_settings,
            _admin_request(),
            settings_router.KnowledgeImageModelSettingsUpdate(model_name="text-only"),
        )

    assert exc_info.value.status_code == 400
    assert "supports_vision" in str(exc_info.value.detail)
