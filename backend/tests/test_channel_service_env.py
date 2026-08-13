from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "app" / "channels" / "service.py"


def _load_service_module(monkeypatch):
    manager = types.ModuleType("app.channels.manager")
    manager.DEFAULT_GATEWAY_URL = "http://localhost:8001"
    manager.DEFAULT_LANGGRAPH_URL = "http://localhost:8001/api"

    class FakeChannelManager:
        def __init__(
            self,
            *,
            bus,
            store,
            langgraph_url,
            gateway_url,
            default_session=None,
            channel_sessions=None,
        ):
            self._langgraph_url = langgraph_url
            self._gateway_url = gateway_url
            self._default_session = default_session
            self._channel_sessions = channel_sessions or {}

    manager.ChannelManager = FakeChannelManager

    message_bus = types.ModuleType("app.channels.message_bus")

    class FakeMessageBus:
        pass

    message_bus.MessageBus = FakeMessageBus

    store = types.ModuleType("app.channels.store")

    class FakeChannelStore:
        pass

    store.ChannelStore = FakeChannelStore

    base = types.ModuleType("app.channels.base")

    class FakeChannel:
        pass

    base.Channel = FakeChannel

    monkeypatch.setitem(sys.modules, "app.channels.manager", manager)
    monkeypatch.setitem(sys.modules, "app.channels.message_bus", message_bus)
    monkeypatch.setitem(sys.modules, "app.channels.store", store)
    monkeypatch.setitem(sys.modules, "app.channels.base", base)

    spec = importlib.util.spec_from_file_location("test_agent_base_channel_service", SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_channel_service_urls_fall_back_to_legacy_env(monkeypatch):
    module = _load_service_module(monkeypatch)
    monkeypatch.setenv("DEER_FLOW_CHANNELS_LANGGRAPH_URL", "http://legacy-gateway:8001/api")
    monkeypatch.setenv("DEER_FLOW_CHANNELS_GATEWAY_URL", "http://legacy-gateway:8001")

    service = module.ChannelService(channels_config={})

    assert service.manager._langgraph_url == "http://legacy-gateway:8001/api"
    assert service.manager._gateway_url == "http://legacy-gateway:8001"


def test_channel_service_urls_prefer_agent_base_env(monkeypatch):
    module = _load_service_module(monkeypatch)
    monkeypatch.setenv("AGENT_BASE_CHANNELS_LANGGRAPH_URL", "http://agent-base-gateway:8001/api")
    monkeypatch.setenv("AGENT_BASE_CHANNELS_GATEWAY_URL", "http://agent-base-gateway:8001")
    monkeypatch.setenv("DEER_FLOW_CHANNELS_LANGGRAPH_URL", "http://legacy-gateway:8001/api")
    monkeypatch.setenv("DEER_FLOW_CHANNELS_GATEWAY_URL", "http://legacy-gateway:8001")

    service = module.ChannelService(channels_config={})

    assert service.manager._langgraph_url == "http://agent-base-gateway:8001/api"
    assert service.manager._gateway_url == "http://agent-base-gateway:8001"


def test_channel_service_config_urls_override_env(monkeypatch):
    module = _load_service_module(monkeypatch)
    monkeypatch.setenv("AGENT_BASE_CHANNELS_LANGGRAPH_URL", "http://agent-base-gateway:8001/api")
    monkeypatch.setenv("AGENT_BASE_CHANNELS_GATEWAY_URL", "http://agent-base-gateway:8001")

    service = module.ChannelService(
        channels_config={
            "langgraph_url": "http://custom-gateway:8001/api",
            "gateway_url": "http://custom-gateway:8001",
        }
    )

    assert service.manager._langgraph_url == "http://custom-gateway:8001/api"
    assert service.manager._gateway_url == "http://custom-gateway:8001"
