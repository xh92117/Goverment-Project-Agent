"""Hard per-task tool-call budgets for isolated subagents."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


def _tool_attempt_number(request: ToolCallRequest, tool_name: str) -> int:
    """Return the 1-based attempt number, including parallel calls in this turn."""
    messages = list((request.state or {}).get("messages") or [])
    completed_attempts = sum(
        1
        for message in messages
        if getattr(message, "type", None) == "tool" and getattr(message, "name", None) == tool_name
    )

    current_id = str(request.tool_call.get("id") or "")
    for message in reversed(messages):
        if getattr(message, "type", None) != "ai":
            continue
        matching_calls = [call for call in (getattr(message, "tool_calls", None) or []) if str(call.get("name") or "") == tool_name]
        for ordinal, call in enumerate(matching_calls, start=1):
            if current_id and str(call.get("id") or "") == current_id:
                return completed_attempts + ordinal
        break

    return completed_attempts + 1


class ToolCallBudgetMiddleware(AgentMiddleware[AgentState]):
    """Block subagent tool calls that exceed configured per-task limits."""

    def __init__(self, limits: Mapping[str, int] | None = None):
        super().__init__()
        self.limits = {str(name): int(limit) for name, limit in (limits or {}).items()}

    def _blocked_message(self, request: ToolCallRequest) -> ToolMessage | None:
        tool_name = str(request.tool_call.get("name") or "")
        limit = self.limits.get(tool_name)
        if limit is None:
            return None

        attempt = _tool_attempt_number(request, tool_name)
        if attempt <= limit:
            return None

        tool_call_id = str(request.tool_call.get("id") or "missing_tool_call_id")
        return ToolMessage(
            content=(
                f"Error: Subagent tool-call budget exceeded for '{tool_name}'. "
                f"Hard limit: {limit} call(s) per delegated task; blocked attempt: {attempt}. "
                "Stop calling this tool and finish with the evidence already collected."
            ),
            tool_call_id=tool_call_id,
            name=tool_name or "unknown_tool",
            status="error",
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        blocked = self._blocked_message(request)
        if blocked is not None:
            return blocked
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        blocked = self._blocked_message(request)
        if blocked is not None:
            return blocked
        return await handler(request)
