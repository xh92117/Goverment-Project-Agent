"""Agent factory facade for secondary-development projects."""

from __future__ import annotations

from typing import Any


def make_orchestrator_agent(config: Any):
    """Create the default orchestrator agent.

    The orchestrator preserves DeerFlow's subagent decomposition strategy while
    giving downstream projects a neutral import path.
    """
    from deerflow.agents.lead_agent import make_lead_agent

    return make_lead_agent(config)
