"""Prompt facade for Agent Base integrations."""

from __future__ import annotations

from typing import Any


def build_orchestrator_prompt(
    *,
    subagent_enabled: bool = True,
    max_concurrent_subagents: int = 3,
    agent_name: str | None = None,
    available_skills: set[str] | None = None,
    app_config: Any | None = None,
) -> str:
    """Build the default Agent Base orchestrator prompt.

    Subagent orchestration is enabled by default because Agent Base preserves
    DeerFlow's decomposition, delegation, and synthesis strategy.
    """
    from deerflow.agents.lead_agent.prompt import apply_prompt_template

    return apply_prompt_template(
        subagent_enabled=subagent_enabled,
        max_concurrent_subagents=max_concurrent_subagents,
        agent_name=agent_name,
        available_skills=available_skills,
        app_config=app_config,
    )
