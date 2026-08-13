import importlib.util
import sys
import types
from pathlib import Path


def _load_mcp_router_module(monkeypatch):
    module_name = "_agent_base_mcp_router_under_test"
    repo_root = Path(__file__).resolve().parents[2]
    router_path = repo_root / "backend" / "app" / "gateway" / "routers" / "mcp.py"

    fastapi_stub = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        def put(self, *args, **kwargs):
            return lambda fn: fn

    fastapi_stub.APIRouter = APIRouter
    fastapi_stub.HTTPException = HTTPException
    fastapi_stub.Request = object
    fastapi_stub.status = types.SimpleNamespace(
        HTTP_400_BAD_REQUEST=400,
        HTTP_403_FORBIDDEN=403,
    )
    monkeypatch.setitem(sys.modules, "fastapi", fastapi_stub)

    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return dict(self.__dict__)

        def model_copy(self, *, update=None):
            data = self.model_dump()
            data.update(update or {})
            return type(self)(**data)

    pydantic_stub.BaseModel = BaseModel
    pydantic_stub.Field = lambda default=None, **_kwargs: default
    monkeypatch.setitem(sys.modules, "pydantic", pydantic_stub)

    gateway_config_stub = types.ModuleType("app.gateway.config")
    gateway_config_stub.get_gateway_config = lambda: types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "app.gateway.config", gateway_config_stub)

    config_stub = types.ModuleType("deerflow.config.extensions_config")
    config_stub.ExtensionsConfig = type("ExtensionsConfig", (), {})
    config_stub.get_extensions_config = lambda: None
    config_stub.reload_extensions_config = lambda: None
    monkeypatch.setitem(sys.modules, "deerflow.config.extensions_config", config_stub)

    spec = importlib.util.spec_from_file_location(module_name, router_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_allowed_stdio_commands_prefers_agent_base_env(monkeypatch):
    mcp = _load_mcp_router_module(monkeypatch)
    monkeypatch.setenv("AGENT_BASE_MCP_STDIO_COMMAND_ALLOWLIST", "python")
    monkeypatch.setenv("DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST", "ruby")

    allowed = mcp._allowed_stdio_commands()

    assert "python" in allowed
    assert "ruby" not in allowed


def test_allowed_stdio_commands_falls_back_to_legacy_env(monkeypatch):
    mcp = _load_mcp_router_module(monkeypatch)
    monkeypatch.delenv("AGENT_BASE_MCP_STDIO_COMMAND_ALLOWLIST", raising=False)
    monkeypatch.setenv("DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST", "ruby")

    allowed = mcp._allowed_stdio_commands()

    assert {"npx", "uvx", "ruby"} <= allowed
