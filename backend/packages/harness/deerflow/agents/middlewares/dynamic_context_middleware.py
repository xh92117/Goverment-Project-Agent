"""Middleware to inject dynamic context (memory, current date) as a system-reminder.

The system prompt is kept fully static for maximum prefix-cache reuse across users
and sessions.  The current date is always injected.  Per-user memory is also injected
when ``memory.injection_enabled`` is True in the app config.  Both are delivered once
per conversation as a dedicated <system-reminder> HumanMessage inserted before the
first user message (frozen-snapshot pattern).

When a conversation spans midnight the middleware detects the date change and injects
a lightweight date-update reminder as a separate HumanMessage before the current turn.
This correction is persisted so subsequent turns on the new day see a consistent history
and do not re-inject.

Reminder format:

    <system-reminder>
    <memory>...</memory>

    <current_date>2026-05-08, Friday</current_date>
    </system-reminder>

Date-update format:

    <system-reminder>
    <current_date>2026-05-09, Saturday</current_date>
    </system-reminder>
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, override

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

if TYPE_CHECKING:
    from deerflow.config.app_config import AppConfig

logger = logging.getLogger(__name__)

# Upper bound (seconds) for a single _inject() offload.  If the warm-up at
# gateway startup failed silently, the first request may still hit a cold
# tiktoken BPE download that blocks until the OS TCP timeout (~26 min).
# This cap ensures the request degrades gracefully instead of hanging.
_INJECT_TIMEOUT_SECONDS = 5.0

_DATE_RE = re.compile(r"<current_date>([^<]+)</current_date>")
_DYNAMIC_CONTEXT_REMINDER_KEY = "dynamic_context_reminder"
_CONTINUE_AFTER_TOOL_STOP_CONTEXT_KEY = "continue_after_tool_stop"
_CONTINUE_AFTER_TOOL_STOP_REMINDER_KEY = "continue_after_tool_stop_reminder"
_SUMMARY_MESSAGE_NAME = "summary"


def _extract_date(content: str) -> str | None:
    """Return the first <current_date> value found in *content*, or None."""
    m = _DATE_RE.search(content)
    return m.group(1) if m else None


def is_dynamic_context_reminder(message: object) -> bool:
    """Return whether *message* is a hidden dynamic-context reminder."""
    return isinstance(message, HumanMessage) and bool(message.additional_kwargs.get(_DYNAMIC_CONTEXT_REMINDER_KEY))


def _last_injected_date(messages: list) -> str | None:
    """Scan messages in reverse and return the most recently injected date.

    Detection uses the ``dynamic_context_reminder`` additional_kwargs flag rather
    than content substring matching, so user messages containing ``<system-reminder>``
    are not mistakenly treated as injected reminders.
    """
    for msg in reversed(messages):
        if is_dynamic_context_reminder(msg):
            content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
            return _extract_date(content_str)
    return None


def _is_user_injection_target(message: object) -> bool:
    """Return whether *message* can receive a dynamic-context reminder."""
    return isinstance(message, HumanMessage) and not is_dynamic_context_reminder(message) and message.name != _SUMMARY_MESSAGE_NAME


def _continue_after_tool_stop_requested(runtime_context: object) -> bool:
    return isinstance(runtime_context, dict) and runtime_context.get(_CONTINUE_AFTER_TOOL_STOP_CONTEXT_KEY) is True


class DynamicContextMiddleware(AgentMiddleware):
    """Inject memory and current date into HumanMessages as a <system-reminder>.

    First turn
    ----------
    Prepends a full system-reminder (memory + date) to the first HumanMessage and
    persists it (same message ID).  The first message is then frozen for the whole
    session — its content never changes again, so the prefix cache can hit on every
    subsequent turn.

    Midnight crossing
    -----------------
    If the conversation spans midnight, the current date differs from the date that
    was injected earlier.  In that case a lightweight date-update reminder is prepended
    to the **current** (last) HumanMessage and persisted.  Subsequent turns on the new
    day see the corrected date in history and skip re-injection.
    """

    def __init__(self, agent_name: str | None = None, *, app_config: AppConfig | None = None):
        super().__init__()
        self._agent_name = agent_name
        self._app_config = app_config

    def _build_full_reminder(self, runtime_context: object = None) -> str:
        from deerflow.agents.lead_agent.prompt import _get_memory_context

        # Memory injection is gated by injection_enabled; date is always included.
        injection_enabled = self._app_config.memory.injection_enabled if self._app_config else True
        memory_context = ""
        context = runtime_context if isinstance(runtime_context, dict) else {}
        project_id_value = context.get("project_id")
        project_id = str(project_id_value).strip() if project_id_value is not None else ""
        if injection_enabled and project_id:
            from deerflow.agents.memory.project import format_project_memory_for_injection, get_project_memory_storage
            from deerflow.runtime.user_context import DEFAULT_USER_ID

            applicant_id = context.get("applicant_id") or "default"
            user_id = str(context.get("user_id") or DEFAULT_USER_ID)
            project_memory = get_project_memory_storage().load(
                project_id,
                applicant_id=applicant_id,
                user_id=user_id,
            )
            max_tokens = self._app_config.memory.max_injection_tokens if self._app_config else 2000
            formatted = format_project_memory_for_injection(project_memory, max_tokens=max_tokens)
            if formatted:
                memory_context = f"<project_memory>\n{formatted}\n</project_memory>\n"
        elif injection_enabled:
            from deerflow.agents.memory.project import GOVERNMENT_PROJECT_AGENT_NAME

            # Government-project runs are not allowed to fall back to the
            # legacy cross-project user profile when the scope is absent.
            if self._agent_name != GOVERNMENT_PROJECT_AGENT_NAME:
                memory_context = _get_memory_context(self._agent_name, app_config=self._app_config)
        current_date = datetime.now().strftime("%Y-%m-%d, %A")

        lines: list[str] = ["<system-reminder>"]
        if memory_context:
            lines.append(memory_context.strip())
            lines.append("")  # blank line separating memory from date
        lines.append(f"<current_date>{current_date}</current_date>")
        lines.append("</system-reminder>")

        return "\n".join(lines)

    def _build_date_update_reminder(self) -> str:
        current_date = datetime.now().strftime("%Y-%m-%d, %A")
        return "\n".join(
            [
                "<system-reminder>",
                f"<current_date>{current_date}</current_date>",
                "</system-reminder>",
            ]
        )

    def _build_continue_after_tool_stop_reminder(self) -> str:
        return "\n".join(
            [
                "<system-reminder>",
                "<continue_after_tool_stop>",
                "用户发送了简短的“继续”请求，且前一轮因为工具调用次数超过安全上限或未生成最终回答而停止。",
                "请基于前文已经检索、读取和工具返回的资料继续完成最终回答；优先直接组织答案。",
                "除非确有必要，不要重复执行检索、读取、glob、ls 等工具，也不要扩大检索范围。",
                "</continue_after_tool_stop>",
                "</system-reminder>",
            ]
        )

    @staticmethod
    def _make_reminder_and_user_messages(original: HumanMessage, reminder_content: str) -> tuple[HumanMessage, HumanMessage]:
        """Return (reminder_msg, user_msg) using the ID-swap technique.

        reminder_msg takes the original message's ID so that add_messages replaces it
        in-place (preserving position).  user_msg carries the original content with a
        derived ``{id}__user`` ID and is appended immediately after by add_messages.

        If the original message has no ID a stable UUID is generated so the derived
        ``{id}__user`` ID never collapses to the ambiguous ``None__user`` string.
        """
        stable_id = original.id or str(uuid.uuid4())
        reminder_msg = HumanMessage(
            content=reminder_content,
            id=stable_id,
            additional_kwargs={"hide_from_ui": True, _DYNAMIC_CONTEXT_REMINDER_KEY: True},
        )
        user_msg = HumanMessage(
            content=original.content,
            id=f"{stable_id}__user",
            name=original.name,
            additional_kwargs=original.additional_kwargs,
        )
        return reminder_msg, user_msg

    def _inject(self, state, runtime_context: object = None) -> dict | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None

        continue_after_tool_stop = _continue_after_tool_stop_requested(runtime_context)
        current_date = datetime.now().strftime("%Y-%m-%d, %A")
        last_date = _last_injected_date(messages)
        logger.debug(
            "DynamicContextMiddleware._inject: msg_count=%d last_date=%r current_date=%r continue_after_tool_stop=%s",
            len(messages),
            last_date,
            current_date,
            continue_after_tool_stop,
        )

        if last_date is None:
            # ── First turn: inject full reminder as a separate HumanMessage ─────
            first_idx = next((i for i, m in enumerate(messages) if _is_user_injection_target(m)), None)
            if first_idx is None:
                return None
            full_reminder = self._build_full_reminder(runtime_context)
            if continue_after_tool_stop:
                full_reminder = "\n\n".join([full_reminder, self._build_continue_after_tool_stop_reminder()])
            logger.info(
                "DynamicContextMiddleware: injecting full reminder (len=%d, has_memory=%s) into first HumanMessage id=%r",
                len(full_reminder),
                "<memory>" in full_reminder or "<project_memory>" in full_reminder,
                messages[first_idx].id,
            )
            reminder_msg, user_msg = self._make_reminder_and_user_messages(messages[first_idx], full_reminder)
            return {"messages": [reminder_msg, user_msg]}

        if continue_after_tool_stop:
            last_human_idx = next((i for i in reversed(range(len(messages))) if _is_user_injection_target(messages[i])), None)
            if last_human_idx is None:
                return None
            reminder_msg, user_msg = self._make_reminder_and_user_messages(
                messages[last_human_idx],
                self._build_continue_after_tool_stop_reminder(),
            )
            reminder_msg.additional_kwargs[_CONTINUE_AFTER_TOOL_STOP_REMINDER_KEY] = True
            logger.info("DynamicContextMiddleware: injected continue-after-tool-stop reminder before current turn")
            return {"messages": [reminder_msg, user_msg]}

        if last_date == current_date:
            # ── Same day: nothing to do ──────────────────────────────────────────
            return None

        # ── Midnight crossed: inject date-update reminder as a separate HumanMessage ──
        last_human_idx = next((i for i in reversed(range(len(messages))) if _is_user_injection_target(messages[i])), None)
        if last_human_idx is None:
            return None

        reminder_msg, user_msg = self._make_reminder_and_user_messages(messages[last_human_idx], self._build_date_update_reminder())
        logger.info("DynamicContextMiddleware: midnight crossing detected — injected date update before current turn")
        return {"messages": [reminder_msg, user_msg]}

    @override
    def before_agent(self, state, runtime: Runtime) -> dict | None:
        return self._inject(state, runtime.context)

    @override
    async def abefore_agent(self, state, runtime: Runtime) -> dict | None:
        # _inject() performs synchronous file I/O (memory JSON loading) and
        # potentially blocking network calls (tiktoken encoding download on
        # first use).  Offload to a thread so the event loop is never blocked
        # — a blocking call here starves all concurrent HTTP handlers (auth,
        # SSE heartbeats, etc.).  See issue #3402.
        #
        # Bounded timeout: if startup warm-up failed silently (e.g. network
        # blip during deploy), the first request's cold tiktoken download can
        # block for tens of minutes (OS TCP timeout).  Time-box injection so
        # the request degrades gracefully (no memory context) rather than
        # hanging.
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._inject, state, runtime.context),
                timeout=_INJECT_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning(
                "DynamicContextMiddleware: injection timed out (%.1fs); skipping memory/date injection for this turn",
                _INJECT_TIMEOUT_SECONDS,
            )
            return None
