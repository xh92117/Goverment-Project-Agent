"""Subagent facade for Agent Base integrations."""
# ruff: noqa: F822

__all__ = [
    "SubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "get_available_subagent_names",
    "get_subagent_config",
    "list_subagents",
]


def __getattr__(name: str):
    if name in __all__:
        from importlib import import_module

        return getattr(import_module("deerflow.subagents"), name)
    raise AttributeError(name)
