import sys
import types
from pathlib import Path


def test_agent_base_exposes_neutral_embedded_client_alias():
    from agent_base import AgentBaseClient as PackageClient
    from agent_base.client import AgentBaseClient

    assert AgentBaseClient.__name__ == "AgentBaseClient"
    assert PackageClient is AgentBaseClient


def test_agent_base_client_lazily_constructs_compatibility_client(monkeypatch):
    fake_client_module = types.ModuleType("deerflow.client")

    class FakeDeerFlowClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    fake_client_module.DeerFlowClient = FakeDeerFlowClient
    monkeypatch.setitem(sys.modules, "deerflow.client", fake_client_module)

    from agent_base.client import AgentBaseClient

    client = AgentBaseClient("model-a", subagent_enabled=True)

    assert isinstance(client, FakeDeerFlowClient)
    assert client.args == ("model-a",)
    assert client.kwargs == {"subagent_enabled": True}


def test_agent_base_client_lazily_exposes_stream_event(monkeypatch):
    fake_client_module = types.ModuleType("deerflow.client")

    class FakeStreamEvent:
        pass

    fake_client_module.StreamEvent = FakeStreamEvent
    monkeypatch.setitem(sys.modules, "deerflow.client", fake_client_module)

    import agent_base.client as client_module

    assert client_module.StreamEvent is FakeStreamEvent


def test_agent_base_exposes_orchestrator_agent_factory():
    from agent_base.agents import make_orchestrator_agent

    assert callable(make_orchestrator_agent)


def test_agent_base_agents_facade_lazily_forwards_orchestrator_factory(monkeypatch):
    fake_lead_agent = types.ModuleType("deerflow.agents.lead_agent")
    calls = []

    def fake_make_lead_agent(config):
        calls.append(config)
        return {"agent": config}

    fake_lead_agent.make_lead_agent = fake_make_lead_agent
    monkeypatch.setitem(sys.modules, "deerflow.agents.lead_agent", fake_lead_agent)

    from agent_base.agents import make_orchestrator_agent

    config = {"name": "demo"}

    assert make_orchestrator_agent(config) == {"agent": config}
    assert calls == [config]


def test_agent_base_config_facade_exposes_common_runtime_config():
    import agent_base.config as config

    assert "Paths" in config.__all__
    assert callable(config.get_app_config)
    assert callable(config.get_paths)


def test_agent_base_config_facade_lazily_forwards_functions(monkeypatch):
    fake_config = types.ModuleType("deerflow.config")
    fake_config.get_app_config = lambda marker=None: {"marker": marker}
    monkeypatch.setitem(sys.modules, "deerflow.config", fake_config)

    import agent_base.config as config

    assert config.get_app_config("ok") == {"marker": "ok"}


def test_agent_base_config_facade_lazily_exposes_models(monkeypatch):
    fake_paths = types.ModuleType("deerflow.config.paths")

    class FakePaths:
        pass

    fake_paths.Paths = FakePaths
    monkeypatch.setitem(sys.modules, "deerflow.config.paths", fake_paths)

    import agent_base.config as config

    assert config.Paths is FakePaths


def test_agent_base_runtime_facade_exposes_run_types():
    import agent_base.runtime as runtime

    assert "RunManager" in runtime.__all__
    assert "RunStatus" in runtime.__all__
    assert "ThreadState" in runtime.__all__


def test_agent_base_runtime_facade_lazily_forwards_runtime_symbols(monkeypatch):
    fake_runtime = types.ModuleType("deerflow.runtime")
    fake_runtime.RunStatus = "fake-run-status"
    monkeypatch.setitem(sys.modules, "deerflow.runtime", fake_runtime)

    import agent_base.runtime as runtime

    assert runtime.RunStatus == "fake-run-status"


def test_agent_base_runtime_facade_lazily_exposes_thread_state(monkeypatch):
    fake_thread_state = types.ModuleType("deerflow.agents.thread_state")

    class FakeThreadState:
        pass

    fake_thread_state.ThreadState = FakeThreadState
    monkeypatch.setitem(sys.modules, "deerflow.agents.thread_state", fake_thread_state)

    import agent_base.runtime as runtime

    assert runtime.ThreadState is FakeThreadState


def test_agent_base_subagents_facade_exposes_registry_and_types():
    import agent_base.subagents as subagents

    assert "SubagentConfig" in subagents.__all__
    assert "get_available_subagent_names" in subagents.__all__
    assert "get_subagent_config" in subagents.__all__
    assert "list_subagents" in subagents.__all__


def test_agent_base_subagents_facade_lazily_forwards_registry(monkeypatch):
    fake_subagents = types.ModuleType("deerflow.subagents")
    fake_subagents.list_subagents = lambda: ["general-purpose", "bash"]
    monkeypatch.setitem(sys.modules, "deerflow.subagents", fake_subagents)

    import agent_base.subagents as subagents

    assert subagents.list_subagents() == ["general-purpose", "bash"]


def test_agent_base_prompt_facade_defaults_to_subagent_orchestration():
    from agent_base.prompt import build_orchestrator_prompt

    defaults = build_orchestrator_prompt.__kwdefaults__ or {}

    assert defaults["subagent_enabled"] is True


def test_agent_base_prompt_facade_lazily_forwards_prompt_builder(monkeypatch):
    fake_prompt = types.ModuleType("deerflow.agents.lead_agent.prompt")
    calls = []

    def fake_apply_prompt_template(**kwargs):
        calls.append(kwargs)
        return "prompt"

    fake_prompt.apply_prompt_template = fake_apply_prompt_template
    monkeypatch.setitem(sys.modules, "deerflow.agents.lead_agent.prompt", fake_prompt)

    from agent_base.prompt import build_orchestrator_prompt

    assert build_orchestrator_prompt(agent_name="assistant", available_skills={"search"}) == "prompt"
    assert calls == [
        {
            "subagent_enabled": True,
            "max_concurrent_subagents": 3,
            "agent_name": "assistant",
            "available_skills": {"search"},
            "app_config": None,
        }
    ]


def test_lead_prompt_preserves_neutral_subagent_orchestration_contract():
    prompt_source = (Path(__file__).parent.parent / "packages" / "harness" / "deerflow" / "agents" / "lead_agent" / "prompt.py").read_text(encoding="utf-8")

    assert "Agent Base" in prompt_source
    assert "open-source super agent" not in prompt_source
    assert "SUBAGENT ORCHESTRATION ACTIVE" in prompt_source
    assert "DECOMPOSE" in prompt_source
    assert "DELEGATE" in prompt_source
    assert "SYNTHESIZE" in prompt_source
