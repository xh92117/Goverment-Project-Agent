from types import SimpleNamespace

from deerflow.config.execution_modes_config import ExecutionModesConfig
from deerflow.subagents.config import SubagentConfig
from deerflow.tools.builtins.task_tool import _apply_execution_mode_subagent_budget


def test_deep_execution_mode_raises_subagent_min_budget():
    config = SubagentConfig(
        name="researcher",
        description="Research task",
        max_turns=4,
        timeout_seconds=180,
    )
    runtime = SimpleNamespace(context={"execution_mode": "deep"}, config={"configurable": {}})
    app_config = SimpleNamespace(execution_modes=ExecutionModesConfig())

    updated = _apply_execution_mode_subagent_budget(config, runtime, app_config)

    assert updated.max_turns == 16
    assert updated.timeout_seconds == 600


def test_standard_execution_mode_keeps_subagent_budget():
    config = SubagentConfig(
        name="researcher",
        description="Research task",
        max_turns=4,
        timeout_seconds=180,
    )
    runtime = SimpleNamespace(context={"execution_mode": "standard"}, config={"configurable": {}})
    app_config = SimpleNamespace(execution_modes=ExecutionModesConfig())

    updated = _apply_execution_mode_subagent_budget(config, runtime, app_config)

    assert updated is config
