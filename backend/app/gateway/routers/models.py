import asyncio
import json
import os
import re
import time
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from app.gateway.config import get_gateway_config
from app.gateway.deps import get_config
from app.gateway.env_file import env_path_for_config, read_env_file, write_env_values
from deerflow.config.app_config import AppConfig, reload_app_config
from deerflow.config.runtime_paths import runtime_home
from deerflow.models import create_chat_model

router = APIRouter(prefix="/api", tags=["models"])


class ModelResponse(BaseModel):
    """Response model for model information."""

    name: str = Field(..., description="Unique identifier for the model")
    model: str = Field(..., description="Actual provider model identifier")
    display_name: str | None = Field(None, description="Human-readable name")
    description: str | None = Field(None, description="Model description")
    supports_thinking: bool = Field(default=False, description="Whether model supports thinking mode")
    supports_reasoning_effort: bool = Field(default=False, description="Whether model supports reasoning effort")


class TokenUsageResponse(BaseModel):
    """Token usage display configuration."""

    enabled: bool = Field(default=False, description="Whether token usage display is enabled")


class ModelsListResponse(BaseModel):
    """Response model for listing all models."""

    models: list[ModelResponse]
    token_usage: TokenUsageResponse


class ModelTestRequest(BaseModel):
    """Request model for a lightweight model connectivity test."""

    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0, description="Maximum seconds to wait for the provider response")
    prompt: str = Field(default="Reply with OK.", max_length=200, description="Short prompt used for the connectivity check")


class ModelTestResponse(BaseModel):
    """Response model for testing a configured model."""

    name: str
    ok: bool
    latency_ms: int
    message: str


class ManagedModelConfig(BaseModel):
    """Editable model configuration exposed by the management API."""

    name: str
    provider: str | None = None
    display_name: str | None = None
    description: str | None = None
    use: str = "langchain_openai:ChatOpenAI"
    model: str
    base_url: str | None = None
    api_key: str | None = None
    request_timeout: float | None = None
    max_retries: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    supports_thinking: bool = False
    supports_reasoning_effort: bool = False
    supports_vision: bool = False
    extra_config: dict[str, Any] = Field(default_factory=dict)


class ManagedModelCreateRequest(BaseModel):
    """Simplified request used by the settings page to create a model."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    display_name: str | None = None
    model: str | None = None
    url: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    description: str | None = None
    use: str | None = None
    request_timeout: float | None = None
    max_retries: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    supports_thinking: bool = False
    supports_reasoning_effort: bool = False
    supports_vision: bool = False
    extra_config: dict[str, Any] = Field(default_factory=dict)


class ManagedModelsResponse(BaseModel):
    """Response model for editable model configuration."""

    models: list[ManagedModelConfig]


class ModelConfigVersion(BaseModel):
    """A restorable config.yaml snapshot created before model config changes."""

    id: str
    created_at: str
    reason: str
    model_count: int


class ModelConfigVersionsResponse(BaseModel):
    """Response model for model config history."""

    versions: list[ModelConfigVersion]


class ModelConfigRestoreResponse(ManagedModelsResponse):
    """Response model after restoring a model config snapshot."""

    restored_version: ModelConfigVersion


class ModelConfigFieldDiff(BaseModel):
    """A single editable field difference between current config and a snapshot."""

    field: str
    current: Any = None
    version: Any = None


class ModelConfigModelDiff(BaseModel):
    """A model-level difference between current config and a snapshot."""

    name: str
    status: str
    fields: list[ModelConfigFieldDiff] = Field(default_factory=list)


class ModelConfigDiffResponse(BaseModel):
    """Response model for comparing current model config with a snapshot."""

    version: ModelConfigVersion
    summary: dict[str, int]
    models: list[ModelConfigModelDiff]


_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{12,}"),
    re.compile(r"(api[_-]?key|authorization|token)(['\"\s:=]+)([^'\"\s,;]+)", re.IGNORECASE),
)
_MASKED_VALUE = "***"
_DEFAULT_MANAGED_MODEL_PROVIDER = "langchain_openai:ChatOpenAI"
_MODEL_NAME_SAFE_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")
_ENV_REFERENCE_PATTERN = re.compile(r"^\$([A-Z_][A-Z0-9_]*)$")
_ENV_NAME_UNSAFE_PATTERN = re.compile(r"[^A-Z0-9_]+")
_PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "url": "https://api.deepseek.com/v1",
        "use": "deerflow.models.patched_deepseek:PatchedChatDeepSeek",
        "url_field": "api_base",
    },
    "openai": {"url": "https://api.openai.com/v1", "use": "langchain_openai:ChatOpenAI"},
    "anthropic": {"url": "https://api.anthropic.com", "use": "langchain_anthropic:ChatAnthropic"},
    "google": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "use": "deerflow.models.patched_openai:PatchedChatOpenAI",
    },
    "qwen": {"url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "use": "langchain_openai:ChatOpenAI"},
    "moonshot": {"url": "https://api.moonshot.cn/v1", "use": "langchain_openai:ChatOpenAI"},
    "zhipu": {"url": "https://open.bigmodel.cn/api/paas/v4", "use": "langchain_openai:ChatOpenAI"},
    "minimax": {"url": "https://api.minimaxi.com/v1", "use": "deerflow.models.patched_minimax:PatchedChatMiniMax"},
    "baidu": {"url": "https://qianfan.baidubce.com/v2", "use": "langchain_openai:ChatOpenAI"},
    "tencent": {"url": "https://api.hunyuan.cloud.tencent.com/v1", "use": "langchain_openai:ChatOpenAI"},
    "volcengine": {"url": "https://ark.cn-beijing.volces.com/api/v3", "use": "langchain_openai:ChatOpenAI"},
    "siliconflow": {"url": "https://api.siliconflow.cn/v1", "use": "langchain_openai:ChatOpenAI"},
    "openrouter": {"url": "https://openrouter.ai/api/v1", "use": "langchain_openai:ChatOpenAI"},
    "ollama": {"url": "http://127.0.0.1:11434/v1", "use": "langchain_openai:ChatOpenAI"},
    "mimo": {"url": "https://api.xiaomimimo.com/v1", "use": "deerflow.models.patched_mimo:PatchedChatMiMo"},
}
_PROVIDER_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "baidu": "QIANFAN_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GEMINI_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "mimo": "MIMO_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "siliconflow": "SILICONFLOW_API_KEY",
    "tencent": "HUNYUAN_API_KEY",
    "volcengine": "VOLCENGINE_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
}
_MANAGED_MODEL_FIELDS = {
    "name",
    "provider",
    "display_name",
    "description",
    "use",
    "model",
    "base_url",
    "api_key",
    "request_timeout",
    "max_retries",
    "max_tokens",
    "temperature",
    "supports_thinking",
    "supports_reasoning_effort",
    "supports_vision",
}
_VERSION_ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9_.-]+$")


async def _require_admin_user(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if user is not None:
        if getattr(user, "system_role", None) != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required to manage model configuration.",
            )
        return

    if not get_gateway_config().enable_local_auth:
        return

    if user is None:
        from app.gateway.deps import get_current_user_from_request

        user = await get_current_user_from_request(request)

    if getattr(user, "system_role", None) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to manage model configuration.",
        )


def _load_raw_config(config_path: Path) -> dict[str, Any]:
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="config.yaml must contain a mapping at the top level")
    return data


def _write_raw_config(config_path: Path, data: dict[str, Any]) -> None:
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def _raw_models(data: dict[str, Any]) -> list[dict[str, Any]]:
    models = data.setdefault("models", [])
    if not isinstance(models, list):
        raise HTTPException(status_code=500, detail="config.yaml models field must be a list")
    return models


def _managed_model_from_raw(raw: dict[str, Any]) -> ManagedModelConfig:
    known = {key: raw.get(key) for key in _MANAGED_MODEL_FIELDS if key in raw}
    if known.get("api_key"):
        known["api_key"] = _MASKED_VALUE
    extra_config = {key: value for key, value in raw.items() if key not in _MANAGED_MODEL_FIELDS}
    return ManagedModelConfig(**known, extra_config=extra_config)


def _raw_model_from_managed(
    model: ManagedModelConfig,
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = {
        **(existing or {}),
        **model.extra_config,
        **model.model_dump(
            exclude_none=True,
            exclude={"extra_config"},
        ),
    }
    if model.api_key == _MASKED_VALUE:
        if existing and existing.get("api_key"):
            data["api_key"] = existing["api_key"]
        else:
            data.pop("api_key", None)
    elif model.api_key == "":
        data.pop("api_key", None)
    return data


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_reference_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _ENV_REFERENCE_PATTERN.fullmatch(value.strip())
    return match.group(1) if match else None


def _infer_model_provider(model: dict[str, Any]) -> str | None:
    provider = _clean_optional_text(str(model.get("provider") or ""))
    if provider:
        return provider.lower()
    signature = " ".join(str(model.get(field) or "").lower() for field in ("name", "model", "use", "base_url", "api_base"))
    for candidate in _PROVIDER_API_KEY_ENV:
        if candidate in signature:
            return candidate
    if "dashscope" in signature:
        return "qwen"
    if "bigmodel" in signature:
        return "zhipu"
    return None


def _model_specific_api_key_env(model: dict[str, Any]) -> str:
    raw_name = str(model.get("name") or model.get("model") or "CUSTOM_MODEL").upper()
    safe_name = _ENV_NAME_UNSAFE_PATTERN.sub("_", raw_name).strip("_") or "CUSTOM_MODEL"
    return f"MODEL_{safe_name}_API_KEY"


def _select_api_key_env_name(
    model: dict[str, Any],
    secret: str,
    env_values: dict[str, str],
    *,
    preferred: str | None = None,
) -> str:
    candidate = preferred
    if candidate is None:
        provider = _infer_model_provider(model)
        candidate = _PROVIDER_API_KEY_ENV.get(provider or "") or _model_specific_api_key_env(model)

    existing_value = env_values.get(candidate)
    if existing_value is None:
        existing_value = os.environ.get(candidate)
    if preferred is not None or existing_value in (None, "", secret):
        return candidate

    base_name = _model_specific_api_key_env(model)
    candidate = base_name
    suffix = 1
    while True:
        existing_value = env_values.get(candidate)
        if existing_value is None:
            existing_value = os.environ.get(candidate)
        if existing_value in (None, "", secret):
            return candidate
        suffix += 1
        candidate = f"{base_name}_{suffix}"


def _externalize_model_api_key(
    config_path: Path,
    model: dict[str, Any],
    requested_api_key: str | None,
    *,
    existing: dict[str, Any] | None = None,
) -> None:
    if requested_api_key == _MASKED_VALUE or (requested_api_key is None and existing is not None):
        value = (existing or {}).get("api_key")
    else:
        value = requested_api_key

    if value in (None, ""):
        model.pop("api_key", None)
        return

    value = str(value).strip()
    reference_name = _env_reference_name(value)
    if reference_name:
        model["api_key"] = f"${reference_name}"
        return

    existing_reference = None
    if requested_api_key != _MASKED_VALUE:
        existing_reference = _env_reference_name((existing or {}).get("api_key"))
    env_path = env_path_for_config(config_path)
    env_values = read_env_file(env_path)
    env_name = _select_api_key_env_name(
        model,
        value,
        env_values,
        preferred=existing_reference,
    )
    write_env_values(env_path, {env_name: value})
    os.environ[env_name] = value
    model["api_key"] = f"${env_name}"


def _externalize_existing_model_api_keys(config_path: Path, data: dict[str, Any]) -> None:
    for model in _raw_models(data):
        if not isinstance(model, dict):
            continue
        value = model.get("api_key")
        if value and not _env_reference_name(value):
            _externalize_model_api_key(
                config_path,
                model,
                _MASKED_VALUE,
                existing=model,
            )


def _model_name_slug(value: str | None) -> str:
    cleaned = _clean_optional_text(value)
    if not cleaned:
        return "custom-model"
    slug = _MODEL_NAME_SAFE_PATTERN.sub("-", cleaned.lower()).strip("-._")
    return slug[:80].strip("-._") or "custom-model"


def _next_available_model_name(base_name: str, models: list[dict[str, Any]]) -> str:
    existing = {str(model.get("name")) for model in models if isinstance(model, dict) and model.get("name")}
    if base_name not in existing:
        return base_name
    suffix = 2
    while f"{base_name}-{suffix}" in existing:
        suffix += 1
    return f"{base_name}-{suffix}"


def _managed_model_from_create_request(
    body: ManagedModelCreateRequest,
    *,
    existing_models: list[dict[str, Any]],
) -> ManagedModelConfig:
    model_identifier = _clean_optional_text(body.model_name) or _clean_optional_text(body.model)
    if not model_identifier:
        raise HTTPException(status_code=400, detail="Model name is required")
    provider = (_clean_optional_text(body.provider) or "custom").lower()
    provider_defaults = _PROVIDER_DEFAULTS.get(provider, {})

    explicit_name = _clean_optional_text(body.name)
    base_name = _model_name_slug(explicit_name or f"{provider}-{model_identifier}")
    if explicit_name:
        name = base_name
        if _find_model_index(existing_models, name) is not None:
            raise HTTPException(status_code=409, detail=f"Model '{name}' already exists")
    else:
        name = _next_available_model_name(base_name, existing_models)

    url = _clean_optional_text(body.url) or _clean_optional_text(body.base_url) or provider_defaults.get("url")
    url_field = provider_defaults.get("url_field", "base_url")
    extra_config = dict(body.extra_config)
    base_url = url
    if url and url_field != "base_url":
        extra_config[url_field] = url
        base_url = None

    return ManagedModelConfig(
        name=name,
        provider=provider,
        display_name=_clean_optional_text(body.display_name) or model_identifier,
        description=_clean_optional_text(body.description),
        use=_clean_optional_text(body.use) or provider_defaults.get("use") or _DEFAULT_MANAGED_MODEL_PROVIDER,
        model=model_identifier,
        base_url=base_url,
        api_key=_clean_optional_text(body.api_key),
        request_timeout=body.request_timeout,
        max_retries=body.max_retries,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        supports_thinking=body.supports_thinking,
        supports_reasoning_effort=body.supports_reasoning_effort,
        supports_vision=body.supports_vision,
        extra_config=extra_config,
    )


def _find_model_index(models: list[dict[str, Any]], model_name: str) -> int | None:
    for index, model in enumerate(models):
        if isinstance(model, dict) and model.get("name") == model_name:
            return index
    return None


def _model_config_versions_dir(config_path: Path) -> Path:
    return runtime_home() / "model_config_versions"


def _snapshot_reason_slug(reason: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", reason.strip())[:80].strip("-")
    return slug or "model-config-change"


def _create_model_config_snapshot(
    config_path: Path,
    reason: str,
    *,
    data: dict[str, Any] | None = None,
) -> ModelConfigVersion:
    snapshot_data = deepcopy(data if data is not None else _load_raw_config(config_path))
    for model in _raw_models(snapshot_data):
        if isinstance(model, dict) and model.get("api_key") and not _env_reference_name(model["api_key"]):
            model.pop("api_key", None)
    model_count = len([model for model in _raw_models(snapshot_data) if isinstance(model, dict)])
    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_version_id = f"{timestamp}_{_snapshot_reason_slug(reason)}"
    versions_dir = _model_config_versions_dir(config_path)
    versions_dir.mkdir(parents=True, exist_ok=True)
    version_id = base_version_id
    suffix = 1
    while (versions_dir / f"{version_id}.yaml").exists() or (versions_dir / f"{version_id}.json").exists():
        suffix += 1
        version_id = f"{base_version_id}.{suffix}"
    _write_raw_config(versions_dir / f"{version_id}.yaml", snapshot_data)
    version = ModelConfigVersion(
        id=version_id,
        created_at=created_at,
        reason=reason,
        model_count=model_count,
    )
    (versions_dir / f"{version_id}.json").write_text(
        json.dumps(version.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return version


def _list_model_config_versions(config_path: Path) -> list[ModelConfigVersion]:
    versions_dir = _model_config_versions_dir(config_path)
    if not versions_dir.exists():
        return []
    versions: list[ModelConfigVersion] = []
    for metadata_path in versions_dir.glob("*.json"):
        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
            version = ModelConfigVersion(**data)
        except Exception:
            continue
        if (versions_dir / f"{version.id}.yaml").exists():
            versions.append(version)
    return sorted(versions, key=lambda item: item.created_at, reverse=True)


def _resolve_model_config_version_path(config_path: Path, version_id: str) -> Path:
    if not _VERSION_ID_PATTERN.fullmatch(version_id):
        raise HTTPException(status_code=400, detail="Invalid model config version id")
    version_path = _model_config_versions_dir(config_path) / f"{version_id}.yaml"
    if not version_path.exists():
        raise HTTPException(status_code=404, detail=f"Model config version '{version_id}' not found")
    return version_path


def _managed_model_map_from_data(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for model in _raw_models(data):
        if not isinstance(model, dict) or not model.get("name"):
            continue
        managed = _managed_model_from_raw(model).model_dump(mode="json")
        result[managed["name"]] = managed
    return result


def _model_field_names(*models: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for model in models:
        names.update(model.keys())
        extra_config = model.get("extra_config")
        if isinstance(extra_config, dict):
            names.update(f"extra_config.{key}" for key in extra_config)
    names.discard("name")
    names.discard("extra_config")
    return sorted(names)


def _model_field_value(model: dict[str, Any], field: str) -> Any:
    if field.startswith("extra_config."):
        extra_config = model.get("extra_config")
        if not isinstance(extra_config, dict):
            return None
        return extra_config.get(field.removeprefix("extra_config."))
    return model.get(field)


def _values_equal(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, ensure_ascii=False, default=str) == json.dumps(
        right,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def _build_model_config_diff(
    current_data: dict[str, Any],
    version_data: dict[str, Any],
    version: ModelConfigVersion,
) -> ModelConfigDiffResponse:
    current_models = _managed_model_map_from_data(current_data)
    version_models = _managed_model_map_from_data(version_data)
    summary = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    diffs: list[ModelConfigModelDiff] = []

    for name in sorted(set(current_models) | set(version_models)):
        current = current_models.get(name)
        previous = version_models.get(name)
        if current is None and previous is not None:
            summary["removed"] += 1
            fields = [
                ModelConfigFieldDiff(
                    field=field,
                    current=None,
                    version=_model_field_value(previous, field),
                )
                for field in _model_field_names(previous)
                if _model_field_value(previous, field) is not None
            ]
            diffs.append(ModelConfigModelDiff(name=name, status="removed", fields=fields))
            continue
        if previous is None and current is not None:
            summary["added"] += 1
            fields = [
                ModelConfigFieldDiff(
                    field=field,
                    current=_model_field_value(current, field),
                    version=None,
                )
                for field in _model_field_names(current)
                if _model_field_value(current, field) is not None
            ]
            diffs.append(ModelConfigModelDiff(name=name, status="added", fields=fields))
            continue

        assert current is not None and previous is not None
        fields = [
            ModelConfigFieldDiff(
                field=field,
                current=_model_field_value(current, field),
                version=_model_field_value(previous, field),
            )
            for field in _model_field_names(current, previous)
            if not _values_equal(
                _model_field_value(current, field),
                _model_field_value(previous, field),
            )
        ]
        if fields:
            summary["changed"] += 1
            diffs.append(ModelConfigModelDiff(name=name, status="changed", fields=fields))
        else:
            summary["unchanged"] += 1
            diffs.append(ModelConfigModelDiff(name=name, status="unchanged", fields=[]))

    return ModelConfigDiffResponse(version=version, summary=summary, models=diffs)


def _managed_models_from_app_config(config: AppConfig) -> ManagedModelsResponse:
    return ManagedModelsResponse(models=[_managed_model_from_raw(model.model_dump(exclude_none=True)) for model in config.models])


def _sanitize_model_test_error(error: BaseException) -> str:
    message = str(error) or error.__class__.__name__
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(api"):
            message = pattern.sub(r"\1\2***", message)
        else:
            message = pattern.sub("***", message)
    return message[:500]


async def _ping_model(model_name: str, body: ModelTestRequest, config: AppConfig) -> ModelTestResponse:
    """Instantiate and invoke a model with a short prompt."""
    model = create_chat_model(
        model_name,
        thinking_enabled=False,
        app_config=config,
        attach_tracing=False,
    )
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=body.prompt)]),
            timeout=body.timeout_seconds,
        )
    except TimeoutError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ModelTestResponse(
            name=model_name,
            ok=False,
            latency_ms=latency_ms,
            message=f"Timed out after {body.timeout_seconds:g} seconds.",
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return ModelTestResponse(
            name=model_name,
            ok=False,
            latency_ms=latency_ms,
            message=_sanitize_model_test_error(exc),
        )

    latency_ms = int((time.perf_counter() - started) * 1000)
    return ModelTestResponse(
        name=model_name,
        ok=True,
        latency_ms=latency_ms,
        message="Model responded successfully.",
    )


@router.get(
    "/models",
    response_model=ModelsListResponse,
    summary="List All Models",
    description="Retrieve a list of all available AI models configured in the system.",
)
async def list_models(config: AppConfig = Depends(get_config)) -> ModelsListResponse:
    """List all available models from configuration.

    Returns model information suitable for frontend display,
    excluding sensitive fields like API keys and internal configuration.

    Returns:
        A list of all configured models with their metadata and token usage display settings.

    Example Response:
        ```json
        {
            "models": [
                {
                    "name": "gpt-4",
                    "model": "gpt-4",
                    "display_name": "GPT-4",
                    "description": "OpenAI GPT-4 model",
                    "supports_thinking": false,
                    "supports_reasoning_effort": false
                },
                {
                    "name": "claude-3-opus",
                    "model": "claude-3-opus",
                    "display_name": "Claude 3 Opus",
                    "description": "Anthropic Claude 3 Opus model",
                    "supports_thinking": true,
                    "supports_reasoning_effort": false
                }
            ],
            "token_usage": {
                "enabled": true
            }
        }
        ```
    """
    models = [
        ModelResponse(
            name=model.name,
            model=model.model,
            display_name=model.display_name,
            description=model.description,
            supports_thinking=model.supports_thinking,
            supports_reasoning_effort=model.supports_reasoning_effort,
        )
        for model in config.models
    ]
    return ModelsListResponse(
        models=models,
        token_usage=TokenUsageResponse(enabled=config.token_usage.enabled),
    )


@router.get(
    "/models/config",
    response_model=ManagedModelsResponse,
    summary="List Editable Model Configuration",
    description="Retrieve editable model configuration with secrets masked.",
)
async def list_model_configuration(request: Request) -> ManagedModelsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    data = _load_raw_config(config_path)
    models = [_managed_model_from_raw(model) for model in _raw_models(data) if isinstance(model, dict)]
    return ManagedModelsResponse(models=models)


@router.post(
    "/models/config",
    response_model=ManagedModelsResponse,
    summary="Create Model Configuration",
    description="Create a model in config.yaml and store any submitted API key in .env.",
)
async def create_model_configuration(
    request: Request,
    body: ManagedModelCreateRequest,
) -> ManagedModelsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    data = _load_raw_config(config_path)
    _externalize_existing_model_api_keys(config_path, data)
    models = _raw_models(data)
    model = _managed_model_from_create_request(body, existing_models=models)
    _create_model_config_snapshot(
        config_path,
        f"before_create_model:{model.name}",
        data=data,
    )
    raw_model = _raw_model_from_managed(model)
    _externalize_model_api_key(
        config_path,
        raw_model,
        model.api_key,
    )
    models.append(raw_model)
    _write_raw_config(config_path, data)
    reloaded = reload_app_config(str(config_path))
    return _managed_models_from_app_config(reloaded)


@router.put(
    "/models/config/{model_name}",
    response_model=ManagedModelsResponse,
    summary="Update Model Configuration",
    description="Update a model in config.yaml and store any submitted API key in .env.",
)
async def update_model_configuration(
    request: Request,
    model_name: str,
    body: ManagedModelConfig,
) -> ManagedModelsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    data = _load_raw_config(config_path)
    models = _raw_models(data)
    index = _find_model_index(models, model_name)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    renamed_index = _find_model_index(models, body.name)
    if renamed_index is not None and renamed_index != index:
        raise HTTPException(status_code=409, detail=f"Model '{body.name}' already exists")
    _externalize_existing_model_api_keys(config_path, data)
    existing = models[index] if isinstance(models[index], dict) else {}
    _create_model_config_snapshot(
        config_path,
        f"before_update_model:{model_name}",
        data=data,
    )
    updated_model = _raw_model_from_managed(body, existing=existing)
    _externalize_model_api_key(
        config_path,
        updated_model,
        body.api_key,
        existing=existing,
    )
    models[index] = updated_model
    _write_raw_config(config_path, data)
    reloaded = reload_app_config(str(config_path))
    return _managed_models_from_app_config(reloaded)


@router.delete(
    "/models/config/{model_name}",
    response_model=ManagedModelsResponse,
    summary="Delete Model Configuration",
    description="Delete a model configuration entry from config.yaml.",
)
async def delete_model_configuration(
    request: Request,
    model_name: str,
) -> ManagedModelsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    data = _load_raw_config(config_path)
    models = _raw_models(data)
    index = _find_model_index(models, model_name)
    if index is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    if len(models) == 1:
        raise HTTPException(status_code=400, detail="At least one model must remain configured")
    _externalize_existing_model_api_keys(config_path, data)
    _create_model_config_snapshot(
        config_path,
        f"before_delete_model:{model_name}",
        data=data,
    )
    del models[index]
    _write_raw_config(config_path, data)
    reloaded = reload_app_config(str(config_path))
    return _managed_models_from_app_config(reloaded)


@router.get(
    "/models/config/versions",
    response_model=ModelConfigVersionsResponse,
    summary="List Model Config Versions",
    description="List restorable config.yaml snapshots created before model configuration changes.",
)
async def list_model_config_versions(request: Request) -> ModelConfigVersionsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    return ModelConfigVersionsResponse(versions=_list_model_config_versions(config_path))


@router.post(
    "/models/config/versions/{version_id}/restore",
    response_model=ModelConfigRestoreResponse,
    summary="Restore Model Config Version",
    description="Restore config.yaml from a previous model configuration snapshot.",
)
async def restore_model_config_version(
    request: Request,
    version_id: str,
) -> ModelConfigRestoreResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    version_path = _resolve_model_config_version_path(config_path, version_id)
    versions = _list_model_config_versions(config_path)
    restored_version = next(
        (version for version in versions if version.id == version_id),
        None,
    )
    if restored_version is None:
        raise HTTPException(status_code=404, detail=f"Model config version '{version_id}' not found")

    current_data = _load_raw_config(config_path)
    _externalize_existing_model_api_keys(config_path, current_data)
    _create_model_config_snapshot(
        config_path,
        f"before_restore_model_config:{version_id}",
        data=current_data,
    )
    restored_data = _load_raw_config(version_path)
    _externalize_existing_model_api_keys(config_path, restored_data)
    _write_raw_config(config_path, restored_data)
    reloaded = reload_app_config(str(config_path))
    models_response = _managed_models_from_app_config(reloaded)
    return ModelConfigRestoreResponse(
        models=models_response.models,
        restored_version=restored_version,
    )


@router.get(
    "/models/config/versions/{version_id}/diff",
    response_model=ModelConfigDiffResponse,
    summary="Diff Model Config Version",
    description="Compare the current config.yaml model settings with a previous snapshot.",
)
async def diff_model_config_version(
    request: Request,
    version_id: str,
) -> ModelConfigDiffResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    version_path = _resolve_model_config_version_path(config_path, version_id)
    versions = _list_model_config_versions(config_path)
    version = next(
        (item for item in versions if item.id == version_id),
        None,
    )
    if version is None:
        raise HTTPException(status_code=404, detail=f"Model config version '{version_id}' not found")

    return _build_model_config_diff(
        current_data=_load_raw_config(config_path),
        version_data=_load_raw_config(version_path),
        version=version,
    )


@router.get(
    "/models/{model_name}",
    response_model=ModelResponse,
    summary="Get Model Details",
    description="Retrieve detailed information about a specific AI model by its name.",
)
async def get_model(model_name: str, config: AppConfig = Depends(get_config)) -> ModelResponse:
    """Get a specific model by name.

    Args:
        model_name: The unique name of the model to retrieve.

    Returns:
        Model information if found.

    Raises:
        HTTPException: 404 if model not found.

    Example Response:
        ```json
        {
            "name": "gpt-4",
            "display_name": "GPT-4",
            "description": "OpenAI GPT-4 model",
            "supports_thinking": false
        }
        ```
    """
    model = config.get_model_config(model_name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    return ModelResponse(
        name=model.name,
        model=model.model,
        display_name=model.display_name,
        description=model.description,
        supports_thinking=model.supports_thinking,
        supports_reasoning_effort=model.supports_reasoning_effort,
    )


@router.post(
    "/models/{model_name}/test",
    response_model=ModelTestResponse,
    summary="Test Model Connectivity",
    description="Invoke a configured model with a short prompt to verify provider connectivity.",
)
async def test_model_connectivity(
    model_name: str,
    body: ModelTestRequest | None = None,
    config: AppConfig = Depends(get_config),
) -> ModelTestResponse:
    """Run a lightweight connectivity check against a configured model."""
    if config.get_model_config(model_name) is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")

    return await _ping_model(model_name, body or ModelTestRequest(), config)
