"""Neutral public facade for the Agent Base harness.

The first refactor phase keeps DeerFlow internals in place and exposes a
brand-neutral API for downstream projects. Later phases can move internals
behind this facade without forcing application code to import ``deerflow``.
"""

__all__ = ["AgentBaseClient", "build_orchestrator_prompt", "make_orchestrator_agent"]


def __getattr__(name: str):
    if name == "AgentBaseClient":
        from .client import AgentBaseClient

        return AgentBaseClient
    if name == "make_orchestrator_agent":
        from .agents import make_orchestrator_agent

        return make_orchestrator_agent
    if name == "build_orchestrator_prompt":
        from .prompt import build_orchestrator_prompt

        return build_orchestrator_prompt
    raise AttributeError(name)
