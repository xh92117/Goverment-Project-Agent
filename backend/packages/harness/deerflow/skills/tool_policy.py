import logging
from typing import Protocol

from deerflow.skills.types import Skill

logger = logging.getLogger(__name__)

_CONDITIONALLY_INJECTED_TOOL_NAMES = frozenset(
    {
        # Added only in plan mode.
        "write_todos",
        # Added only when subagents or custom-agent management are enabled.
        "task",
        "setup_agent",
        "update_agent",
    }
)


class NamedTool(Protocol):
    name: str


def allowed_tool_names_for_skills(skills: list[Skill]) -> set[str] | None:
    """Return the union of explicit skill allowed-tools declarations.

    None means legacy allow-all behavior. It is returned only when no loaded
    skill declares allowed-tools. Once any skill declares the field, legacy
    skills without the field contribute no tools instead of disabling the
    explicit restrictions from other skills.
    """
    if not skills:
        return None

    allowed: set[str] = set()
    has_explicit_declaration = False
    for skill in skills:
        if skill.allowed_tools is None:
            continue
        has_explicit_declaration = True
        if not skill.allowed_tools:
            logger.info("Skill %s declared empty allowed-tools", skill.name)
        allowed.update(skill.allowed_tools)

    if not has_explicit_declaration:
        return None
    return allowed


def filter_tools_by_skill_allowed_tools[ToolT: NamedTool](tools: list[ToolT], skills: list[Skill]) -> list[ToolT]:
    allowed = allowed_tool_names_for_skills(skills)
    if allowed is None:
        return tools

    available = {tool.name for tool in tools}
    missing = sorted(allowed - available - _CONDITIONALLY_INJECTED_TOOL_NAMES)
    if missing:
        skill_names = sorted(skill.name for skill in skills if skill.allowed_tools is not None)
        logger.warning(
            "Skill allowed-tools declare tool(s) not present in current binding: %s (skills: %s). "
            "Prompts or skill instructions that mention these names can trigger invalid tool-call errors.",
            ", ".join(missing),
            ", ".join(skill_names),
        )

    return [tool for tool in tools if tool.name in allowed]
