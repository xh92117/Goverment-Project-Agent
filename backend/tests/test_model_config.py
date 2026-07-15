from deerflow.config.model_config import ModelConfig


def _make_model(**overrides) -> ModelConfig:
    return ModelConfig(
        name="openai-responses",
        display_name="OpenAI Responses",
        description=None,
        use="langchain_openai:ChatOpenAI",
        model="gpt-5",
        **overrides,
    )


def test_responses_api_fields_are_declared_in_model_schema():
    assert "use_responses_api" in ModelConfig.model_fields
    assert "output_version" in ModelConfig.model_fields


def test_responses_api_fields_round_trip_in_model_dump():
    config = _make_model(
        api_key="$OPENAI_API_KEY",
        use_responses_api=True,
        output_version="responses/v1",
    )

    dumped = config.model_dump(exclude_none=True)

    assert dumped["use_responses_api"] is True
    assert dumped["output_version"] == "responses/v1"


class _FakeAppConfig:
    def __init__(self, exists: bool = True):
        self.exists = exists

    def get_model_config(self, name: str):
        return object() if self.exists and name == "test-model" else None


class _SuccessfulChatModel:
    async def ainvoke(self, messages):
        self.messages = messages
        return "OK"


class _FailingChatModel:
    async def ainvoke(self, messages):
        raise RuntimeError("provider rejected api_key=sk-secret1234567890")


def test_model_connectivity_success(monkeypatch):
    import anyio

    from app.gateway.routers import models as models_router

    captured = {}

    def fake_create_chat_model(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _SuccessfulChatModel()

    monkeypatch.setattr(models_router, "create_chat_model", fake_create_chat_model)

    result = anyio.run(
        models_router.test_model_connectivity,
        "test-model",
        models_router.ModelTestRequest(timeout_seconds=1, prompt="ping"),
        _FakeAppConfig(),
    )

    assert result.ok is True
    assert result.name == "test-model"
    assert result.message == "Model responded successfully."
    assert captured["args"] == ("test-model",)
    assert captured["kwargs"]["thinking_enabled"] is False
    assert captured["kwargs"]["attach_tracing"] is False


def test_model_connectivity_returns_404_for_unknown_model():
    import anyio
    import pytest
    from fastapi import HTTPException

    from app.gateway.routers import models as models_router

    with pytest.raises(HTTPException) as excinfo:
        anyio.run(
            models_router.test_model_connectivity,
            "missing-model",
            models_router.ModelTestRequest(timeout_seconds=1),
            _FakeAppConfig(exists=False),
        )

    assert excinfo.value.status_code == 404


def test_model_connectivity_sanitizes_provider_errors(monkeypatch):
    import anyio

    from app.gateway.routers import models as models_router

    monkeypatch.setattr(
        models_router,
        "create_chat_model",
        lambda *args, **kwargs: _FailingChatModel(),
    )

    result = anyio.run(
        models_router.test_model_connectivity,
        "test-model",
        models_router.ModelTestRequest(timeout_seconds=1),
        _FakeAppConfig(),
    )

    assert result.ok is False
    assert "sk-secret" not in result.message
    assert "api_key=" in result.message
    assert "***" in result.message


def _admin_request():
    from types import SimpleNamespace

    return SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(system_role="admin")))


def test_list_model_configuration_masks_api_key(tmp_path, monkeypatch):
    import anyio

    from app.gateway.routers import models as models_router

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: qwen
    use: langchain_openai:ChatOpenAI
    model: qwen-plus
    api_key: $DASHSCOPE_API_KEY
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    result = anyio.run(models_router.list_model_configuration, _admin_request())

    assert len(result.models) == 1
    assert result.models[0].name == "qwen"
    assert result.models[0].api_key == "***"
    assert result.models[0].base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_update_model_configuration_preserves_masked_api_key(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import anyio
    import yaml

    from app.gateway.routers import models as models_router

    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("AGENT_BASE_HOME", str(runtime_home))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: qwen
    use: langchain_openai:ChatOpenAI
    model: qwen-plus
    api_key: $DASHSCOPE_API_KEY
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )
    monkeypatch.setattr(
        models_router,
        "reload_app_config",
        lambda path: SimpleNamespace(
            models=[
                ModelConfig(
                    name="qwen",
                    use="langchain_openai:ChatOpenAI",
                    model="qwen-max",
                    api_key="$DASHSCOPE_API_KEY",
                )
            ]
        ),
    )

    body = models_router.ManagedModelConfig(
        name="qwen",
        use="langchain_openai:ChatOpenAI",
        model="qwen-max",
        api_key="***",
    )
    result = anyio.run(
        models_router.update_model_configuration,
        _admin_request(),
        "qwen",
        body,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["models"][0]["api_key"] == "$DASHSCOPE_API_KEY"
    assert saved["models"][0]["model"] == "qwen-max"
    assert result.models[0].api_key == "***"
    versions_dir = runtime_home / "model_config_versions"
    assert len(list(versions_dir.glob("*.yaml"))) == 1
    assert len(list(versions_dir.glob("*.json"))) == 1


def test_create_model_configuration_accepts_simplified_request(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import anyio
    import yaml

    from app.gateway.routers import models as models_router

    runtime_home = tmp_path / "runtime"
    monkeypatch.setenv("AGENT_BASE_HOME", str(runtime_home))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: existing
    use: langchain_openai:ChatOpenAI
    model: existing-model
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    def fake_reload(path):
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return SimpleNamespace(
            models=[ModelConfig(**model) for model in data["models"]]
        )

    monkeypatch.setattr(models_router, "reload_app_config", fake_reload)

    body = models_router.ManagedModelCreateRequest(
        model_name="deepseek-v4-pro",
        provider="deepseek",
        url="https://api.deepseek.com/v1",
        api_key="$DEEPSEEK_API_KEY",
    )
    result = anyio.run(
        models_router.create_model_configuration,
        _admin_request(),
        body,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    created = saved["models"][1]
    assert created["name"] == "deepseek-deepseek-v4-pro"
    assert created["provider"] == "deepseek"
    assert created["display_name"] == "deepseek-v4-pro"
    assert created["use"] == "deerflow.models.patched_deepseek:PatchedChatDeepSeek"
    assert created["model"] == "deepseek-v4-pro"
    assert created["api_base"] == "https://api.deepseek.com/v1"
    assert created["api_key"] == "$DEEPSEEK_API_KEY"
    assert result.models[1].api_key == "***"
    versions_dir = runtime_home / "model_config_versions"
    assert len(list(versions_dir.glob("*.yaml"))) == 1
    assert len(list(versions_dir.glob("*.json"))) == 1


def test_delete_model_configuration_rejects_last_model(tmp_path, monkeypatch):
    import anyio
    import pytest
    from fastapi import HTTPException

    from app.gateway.routers import models as models_router

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: only
    use: langchain_openai:ChatOpenAI
    model: gpt-test
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    with pytest.raises(HTTPException) as excinfo:
        anyio.run(
            models_router.delete_model_configuration,
            _admin_request(),
            "only",
        )

    assert excinfo.value.status_code == 400


def test_restore_model_config_version_restores_config_yaml(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import anyio
    import yaml

    from app.gateway.routers import models as models_router

    monkeypatch.setenv("AGENT_BASE_HOME", str(tmp_path / "runtime"))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: old
    use: langchain_openai:ChatOpenAI
    model: old-model
""",
        encoding="utf-8",
    )
    version = models_router._create_model_config_snapshot(config_path, "manual")
    config_path.write_text(
        """
models:
  - name: new
    use: langchain_openai:ChatOpenAI
    model: new-model
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    def fake_reload(path):
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return SimpleNamespace(
            models=[ModelConfig(**model) for model in data["models"]]
        )

    monkeypatch.setattr(models_router, "reload_app_config", fake_reload)

    result = anyio.run(
        models_router.restore_model_config_version,
        _admin_request(),
        version.id,
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["models"][0]["name"] == "old"
    assert saved["models"][0]["model"] == "old-model"
    assert result.restored_version.id == version.id
    assert result.models[0].name == "old"


def test_diff_model_config_version_reports_added_removed_and_changed(tmp_path, monkeypatch):
    import anyio

    from app.gateway.routers import models as models_router

    monkeypatch.setenv("AGENT_BASE_HOME", str(tmp_path / "runtime"))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
models:
  - name: shared
    use: langchain_openai:ChatOpenAI
    model: old-model
    api_key: $OLD_KEY
    max_tokens: 1024
    custom_flag: old
  - name: removed
    use: langchain_openai:ChatOpenAI
    model: removed-model
""",
        encoding="utf-8",
    )
    version = models_router._create_model_config_snapshot(config_path, "manual")
    config_path.write_text(
        """
models:
  - name: shared
    use: langchain_openai:ChatOpenAI
    model: new-model
    api_key: $NEW_KEY
    max_tokens: 4096
    custom_flag: new
  - name: added
    use: langchain_openai:ChatOpenAI
    model: added-model
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        models_router.AppConfig,
        "resolve_config_path",
        staticmethod(lambda: config_path),
    )

    result = anyio.run(
        models_router.diff_model_config_version,
        _admin_request(),
        version.id,
    )

    assert result.version.id == version.id
    assert result.summary == {
        "added": 1,
        "removed": 1,
        "changed": 1,
        "unchanged": 0,
    }
    by_name = {item.name: item for item in result.models}
    assert by_name["added"].status == "added"
    assert by_name["removed"].status == "removed"
    assert by_name["shared"].status == "changed"
    changed_fields = {field.field: field for field in by_name["shared"].fields}
    assert changed_fields["model"].current == "new-model"
    assert changed_fields["model"].version == "old-model"
    assert changed_fields["max_tokens"].current == 4096
    assert changed_fields["max_tokens"].version == 1024
    assert changed_fields["extra_config.custom_flag"].current == "new"
    assert changed_fields["extra_config.custom_flag"].version == "old"
    assert "api_key" not in changed_fields
