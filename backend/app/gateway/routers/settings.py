import os
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.gateway.routers.models import _load_raw_config, _require_admin_user, _write_raw_config
from deerflow.config.app_config import AppConfig, reload_app_config

router = APIRouter(prefix="/api/settings", tags=["settings"])

_MASKED_VALUE = "***"
_MINERU_ENV_KEYS = {
    "api_token": "MINERU_API_TOKEN",
    "api_base_url": "MINERU_API_BASE_URL",
    "model_version": "MINERU_MODEL_VERSION",
    "language": "MINERU_LANGUAGE",
    "timeout_seconds": "MINERU_TIMEOUT_SECONDS",
    "poll_interval_seconds": "MINERU_POLL_INTERVAL_SECONDS",
    "max_wait_seconds": "MINERU_MAX_WAIT_SECONDS",
}
_SAFE_ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9_./:@%+=,\-]+$")


class PdfParserSettingsResponse(BaseModel):
    """PDF parser settings persisted in config.yaml and .env."""

    api_token: str = Field(default="", description="Masked MinerU API token when configured")
    token_configured: bool = Field(default=False, description="Whether MinerU API token is configured")
    api_base_url: str = Field(default="https://mineru.net")
    model_version: str = Field(default="vlm")
    language: str = Field(default="ch")
    timeout_seconds: float = Field(default=60, ge=1, le=600)
    poll_interval_seconds: float = Field(default=5, ge=1, le=120)
    max_wait_seconds: float = Field(default=900, ge=30, le=7200)
    pdf_converter: Literal["auto", "pymupdf4llm", "markitdown"] = "auto"
    env_path: str
    config_path: str


class PdfParserSettingsUpdate(BaseModel):
    """Editable PDF parser settings from the settings page."""

    model_config = ConfigDict(extra="forbid")

    api_token: str | None = Field(default=None, max_length=10000)
    clear_token: bool = Field(default=False)
    api_base_url: str = Field(default="https://mineru.net", max_length=500)
    model_version: str = Field(default="vlm", max_length=100)
    language: str = Field(default="ch", max_length=40)
    timeout_seconds: float = Field(default=60, ge=1, le=600)
    poll_interval_seconds: float = Field(default=5, ge=1, le=120)
    max_wait_seconds: float = Field(default=900, ge=30, le=7200)
    pdf_converter: Literal["auto", "pymupdf4llm", "markitdown"] = "auto"

    @field_validator("api_base_url", "model_version", "language")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be empty")
        return stripped

    @field_validator("api_token")
    @classmethod
    def _strip_optional_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class KnowledgeImageModelOption(BaseModel):
    """Vision-capable model available to knowledge image extraction."""

    name: str
    display_name: str | None = None
    provider: str | None = None
    model: str | None = None


class KnowledgeImageModelSettingsResponse(BaseModel):
    """Current knowledge image model selection and valid choices."""

    selected_model: str | None = None
    selected_model_valid: bool = False
    vision_models: list[KnowledgeImageModelOption] = Field(default_factory=list)


class KnowledgeImageModelSettingsUpdate(BaseModel):
    """Select or clear the model used for knowledge image extraction."""

    model_config = ConfigDict(extra="forbid")

    model_name: str | None = Field(default=None, max_length=200)

    @field_validator("model_name")
    @classmethod
    def _strip_optional_model_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


def _env_path_for_config(config_path: Path) -> Path:
    return config_path.parent / ".env"


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
        if raw.strip().startswith('"'):
            value = value.replace(r"\"", '"').replace(r"\\", "\\")
    return value


def _read_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = _parse_env_value(value)
    return values


def _format_env_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise HTTPException(status_code=400, detail="Environment values cannot contain newlines")
    if value and _SAFE_ENV_VALUE_RE.fullmatch(value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', r"\"") + '"'


def _write_env_values(env_path: Path, updates: dict[str, str | None]) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for raw_line in existing_lines:
        stripped = raw_line.strip()
        prefix = ""
        line = stripped
        if line.startswith("export "):
            prefix = "export "
            line = line.removeprefix("export ").lstrip()
        if not line or line.startswith("#") or "=" not in line:
            output.append(raw_line)
            continue

        key = line.split("=", 1)[0].strip()
        if key not in updates:
            output.append(raw_line)
            continue

        seen.add(key)
        value = updates[key]
        if value is None:
            continue
        output.append(f"{prefix}{key}={_format_env_value(value)}")

    for key, value in updates.items():
        if key in seen or value is None:
            continue
        output.append(f"{key}={_format_env_value(value)}")

    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _env_value(env_values: dict[str, str], key: str, default: str) -> str:
    value = env_values.get(key)
    if value is None:
        value = os.environ.get(key)
    return str(value if value not in (None, "") else default)


def _float_env_value(env_values: dict[str, str], key: str, default: float) -> float:
    try:
        return float(_env_value(env_values, key, str(default)))
    except (TypeError, ValueError):
        return default


def _uploads_pdf_converter(data: dict) -> Literal["auto", "pymupdf4llm", "markitdown"]:
    uploads = data.get("uploads")
    if not isinstance(uploads, dict):
        return "auto"
    value = str(uploads.get("pdf_converter") or "auto").strip().lower()
    if value in {"auto", "pymupdf4llm", "markitdown"}:
        return value  # type: ignore[return-value]
    return "auto"


def _knowledge_image_model_settings_response(data: dict) -> KnowledgeImageModelSettingsResponse:
    raw_models = data.get("models", [])
    if not isinstance(raw_models, list):
        raise HTTPException(status_code=500, detail="config.yaml models field must be a list")

    vision_models: list[KnowledgeImageModelOption] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, dict) or not bool(raw_model.get("supports_vision", False)):
            continue
        name = str(raw_model.get("name") or "").strip()
        if not name:
            continue
        vision_models.append(
            KnowledgeImageModelOption(
                name=name,
                display_name=str(raw_model.get("display_name") or "").strip() or None,
                provider=str(raw_model.get("provider") or "").strip() or None,
                model=str(raw_model.get("model") or "").strip() or None,
            )
        )

    selected_model = str(data.get("knowledge_image_model") or "").strip() or None
    return KnowledgeImageModelSettingsResponse(
        selected_model=selected_model,
        selected_model_valid=bool(selected_model and any(model.name == selected_model for model in vision_models)),
        vision_models=vision_models,
    )


def _settings_response(config_path: Path, env_path: Path) -> PdfParserSettingsResponse:
    data = _load_raw_config(config_path)
    env_values = _read_env_file(env_path)
    token = env_values.get(_MINERU_ENV_KEYS["api_token"]) or os.environ.get(_MINERU_ENV_KEYS["api_token"], "")
    token_configured = bool(token.strip())
    return PdfParserSettingsResponse(
        api_token=_MASKED_VALUE if token_configured else "",
        token_configured=token_configured,
        api_base_url=_env_value(env_values, _MINERU_ENV_KEYS["api_base_url"], "https://mineru.net"),
        model_version=_env_value(env_values, _MINERU_ENV_KEYS["model_version"], "vlm"),
        language=_env_value(env_values, _MINERU_ENV_KEYS["language"], "ch"),
        timeout_seconds=_float_env_value(env_values, _MINERU_ENV_KEYS["timeout_seconds"], 60),
        poll_interval_seconds=_float_env_value(env_values, _MINERU_ENV_KEYS["poll_interval_seconds"], 5),
        max_wait_seconds=_float_env_value(env_values, _MINERU_ENV_KEYS["max_wait_seconds"], 900),
        pdf_converter=_uploads_pdf_converter(data),
        env_path=str(env_path),
        config_path=str(config_path),
    )


@router.get(
    "/pdf-parser",
    response_model=PdfParserSettingsResponse,
    summary="Get PDF Parser Settings",
    description="Read MinerU PDF parser settings from .env and config.yaml.",
)
async def get_pdf_parser_settings(request: Request) -> PdfParserSettingsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    return _settings_response(config_path, _env_path_for_config(config_path))


@router.put(
    "/pdf-parser",
    response_model=PdfParserSettingsResponse,
    summary="Update PDF Parser Settings",
    description="Persist MinerU PDF parser settings to .env and config.yaml.",
)
async def update_pdf_parser_settings(
    request: Request,
    body: PdfParserSettingsUpdate,
) -> PdfParserSettingsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    env_path = _env_path_for_config(config_path)
    env_values = _read_env_file(env_path)

    existing_token = env_values.get(_MINERU_ENV_KEYS["api_token"]) or os.environ.get(_MINERU_ENV_KEYS["api_token"], "")
    incoming_token = (body.api_token or "").strip()
    if body.clear_token:
        token_value: str | None = None
    elif incoming_token and incoming_token != _MASKED_VALUE:
        token_value = incoming_token
    else:
        token_value = existing_token.strip() or None

    env_updates: dict[str, str | None] = {
        _MINERU_ENV_KEYS["api_token"]: token_value,
        _MINERU_ENV_KEYS["api_base_url"]: body.api_base_url.rstrip("/"),
        _MINERU_ENV_KEYS["model_version"]: body.model_version,
        _MINERU_ENV_KEYS["language"]: body.language,
        _MINERU_ENV_KEYS["timeout_seconds"]: f"{body.timeout_seconds:g}",
        _MINERU_ENV_KEYS["poll_interval_seconds"]: f"{body.poll_interval_seconds:g}",
        _MINERU_ENV_KEYS["max_wait_seconds"]: f"{body.max_wait_seconds:g}",
    }
    _write_env_values(env_path, env_updates)

    for key, value in env_updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    data = _load_raw_config(config_path)
    uploads = data.setdefault("uploads", {})
    if not isinstance(uploads, dict):
        raise HTTPException(status_code=500, detail="config.yaml uploads field must be a mapping")
    uploads["pdf_converter"] = body.pdf_converter
    _write_raw_config(config_path, data)
    reload_app_config(str(config_path))

    return _settings_response(config_path, env_path)


@router.get(
    "/knowledge-image-model",
    response_model=KnowledgeImageModelSettingsResponse,
    summary="Get Knowledge Image Model Settings",
    description="Read the selected knowledge image model and list models with supports_vision enabled.",
)
async def get_knowledge_image_model_settings(request: Request) -> KnowledgeImageModelSettingsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    return _knowledge_image_model_settings_response(_load_raw_config(config_path))


@router.put(
    "/knowledge-image-model",
    response_model=KnowledgeImageModelSettingsResponse,
    summary="Update Knowledge Image Model Settings",
    description="Persist a vision-capable model as the knowledge image extraction model.",
)
async def update_knowledge_image_model_settings(
    request: Request,
    body: KnowledgeImageModelSettingsUpdate,
) -> KnowledgeImageModelSettingsResponse:
    await _require_admin_user(request)
    config_path = AppConfig.resolve_config_path()
    data = _load_raw_config(config_path)
    settings = _knowledge_image_model_settings_response(data)

    if body.model_name and not any(model.name == body.model_name for model in settings.vision_models):
        raise HTTPException(
            status_code=400,
            detail=f"Model {body.model_name} is unavailable or does not enable supports_vision.",
        )

    data["knowledge_image_model"] = body.model_name
    _write_raw_config(config_path, data)
    reload_app_config(str(config_path))
    return _knowledge_image_model_settings_response(data)
