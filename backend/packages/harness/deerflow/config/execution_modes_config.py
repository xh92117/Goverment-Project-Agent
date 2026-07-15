"""Execution-mode budget configuration."""

from typing import Literal

from pydantic import BaseModel, Field

ExecutionModeName = Literal["standard", "deep"]
DEFAULT_EXECUTION_MODE: ExecutionModeName = "standard"


def normalize_execution_mode(value: object) -> ExecutionModeName:
    """Normalize external execution mode input."""
    if isinstance(value, str) and value.strip().lower() == "deep":
        return "deep"
    return "standard"


class ExecutionModeBudgetConfig(BaseModel):
    """Runtime budget knobs applied for a single user run."""

    recursion_limit: int | None = Field(
        default=None,
        ge=1,
        description="Minimum LangGraph recursion limit for this execution mode.",
    )
    subagent_enabled: bool | None = Field(
        default=None,
        description="Whether this mode should explicitly enable subagent delegation.",
    )
    max_concurrent_subagents: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="Minimum concurrent subagent limit for this execution mode.",
    )
    subagent_min_turns: int | None = Field(
        default=None,
        ge=1,
        description="Minimum max_turns applied to each subagent launched in this mode.",
    )
    subagent_min_timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Minimum timeout_seconds applied to each subagent launched in this mode.",
    )


class ExecutionModesConfig(BaseModel):
    """Configured budgets for standard and deep execution modes."""

    standard: ExecutionModeBudgetConfig = Field(
        default_factory=lambda: ExecutionModeBudgetConfig(
            recursion_limit=100,
            max_concurrent_subagents=3,
        ),
    )
    deep: ExecutionModeBudgetConfig = Field(
        default_factory=lambda: ExecutionModeBudgetConfig(
            recursion_limit=200,
            subagent_enabled=True,
            max_concurrent_subagents=4,
            subagent_min_turns=16,
            subagent_min_timeout_seconds=600,
        ),
    )

    def budget_for(self, mode: object) -> ExecutionModeBudgetConfig:
        return getattr(self, normalize_execution_mode(mode))
