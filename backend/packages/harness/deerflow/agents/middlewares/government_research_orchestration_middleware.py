"""Runtime guardrails for government-project complex research orchestration."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.subagents.status_contract import SUBAGENT_STATUS_KEY, extract_subagent_status

logger = logging.getLogger(__name__)

_WEB_TOOLS = {"web_search", "web_fetch", "web_extract"}
_TASK_TOOL = "task"
_MISSING_TOOL_CALL_ID = "missing_tool_call_id"

_COMPLEX_RESEARCH_RE = re.compile(
    r"("
    r"研究现状|文献综述|国内外研究|国内外现状|最新进展|发展趋势|技术路线|"
    r"政策解读|指南分析|申报指南|查阅相关资料|网上查阅|联网查阅|网页查询|网络查询|"
    r"申报依据|立项依据|选题依据|课题依据|申报可行性|可行性论证|申报竞争力|竞争力|"
    r"申报风险|研究基础|技术背景|需求分析|必要性|创新性|"
    r"多源|对比分析|来源对比|事实核验|综合分析|背景调研"
    r")"
)

_SIMPLE_LOOKUP_RE = re.compile(
    r"("
    r"只查|仅查|单个|一个链接|一个网址|具体网址|官网链接|截止日期|电话|地址|"
    r"发布日期|发布时间|文件原文|下载链接"
    r")"
)

_BLOCK_MESSAGE = (
    "错误：这是政府项目申报场景下的复杂研究请求。当前已启用子智能体委派，"
    "主智能体必须先拆解任务，并发起一个聚焦的初始 `task` 批次；至少 1 个，证据领域确实不同时优先 2-3 个，"
    "且不得超过当前运行模式的响应级硬上限。"
    "例如：研究现状/文献/最新进展使用 literature-researcher，"
    "标准/检测方法/专利使用 standards-patent-researcher，"
    "政策通知/申报指南使用 guide-analyzer。子智能体结果返回后再综合；"
    "主智能体只能在补充小缺口或核验特定来源时直接使用 web_search/web_fetch。"
)

_TASK_BUDGET_BLOCK_MESSAGE = (
    "错误：此复杂政府项目研究请求的首批子智能体结果已经返回。"
    "不要在同一用户轮次继续发起 `task` 调用；现在应综合已有子智能体发现。"
    "如仍有小缺口，可在至少一个成功子智能体结果之后由主智能体直接使用 web_search/web_fetch 补充核验。"
)

_TASK_ATTEMPT_BLOCK_MESSAGE = (
    "错误：此复杂政府项目研究请求的子智能体尝试预算已经用尽。"
    "不要继续发起 `task` 调用；请基于已有部分发现生成最终答复，并明确说明失败项或证据不足处。"
)

_SUBAGENT_FAILURE_FALLBACK_MIN_TERMINAL_TASKS = 2


def _can_launch_supplemental_task(completed_tasks: int, terminal_tasks: int) -> bool:
    """Allow one gap-filling task when the first batch only partially succeeded."""
    return completed_tasks == 1 and terminal_tasks == 2


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return str(content) if content is not None else ""


def _latest_human_index(messages: list[Any]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if getattr(message, "type", None) == "human":
            return index
    return None


def _task_result_counts_since(messages: list[Any], start_index: int) -> tuple[int, int]:
    completed = 0
    terminal = 0
    for message in messages[start_index + 1 :]:
        if getattr(message, "type", None) != "tool" or getattr(message, "name", None) != _TASK_TOOL:
            continue
        status = (getattr(message, "additional_kwargs", None) or {}).get(SUBAGENT_STATUS_KEY)
        if not status:
            status = extract_subagent_status(_message_text(message))
        if status == "completed":
            completed += 1
        if status:
            terminal += 1
    return completed, terminal


def _is_complex_research_request(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if _SIMPLE_LOOKUP_RE.search(normalized) and not _COMPLEX_RESEARCH_RE.search(normalized):
        return False
    return bool(_COMPLEX_RESEARCH_RE.search(normalized))


class GovernmentResearchOrchestrationMiddleware(AgentMiddleware[AgentState]):
    """Force complex government-project research through subagents before web loops.

    The prompt asks the model to decompose complex research, but provider tool
    selection is still probabilistic. This middleware makes the orchestration
    rule executable: for a recognized complex research request, lead-agent web
    tools are blocked until at least one task result exists for the latest user
    turn.
    """

    def _blocked_message(self, request: ToolCallRequest) -> ToolMessage | None:
        name = str(request.tool_call.get("name") or "")
        if name not in _WEB_TOOLS and name != _TASK_TOOL:
            return None

        messages = list((request.state or {}).get("messages") or [])
        human_index = _latest_human_index(messages)
        if human_index is None:
            return None

        latest_human_text = _message_text(messages[human_index])
        if not _is_complex_research_request(latest_human_text):
            return None

        completed_tasks, terminal_tasks = _task_result_counts_since(messages, human_index)
        if name == _TASK_TOOL:
            if terminal_tasks >= 3:
                return self._tool_message(request, _TASK_ATTEMPT_BLOCK_MESSAGE)
            if completed_tasks > 0:
                if _can_launch_supplemental_task(completed_tasks, terminal_tasks):
                    return None
                return self._tool_message(request, _TASK_BUDGET_BLOCK_MESSAGE)
            return None

        if completed_tasks > 0:
            return None

        if terminal_tasks >= _SUBAGENT_FAILURE_FALLBACK_MIN_TERMINAL_TASKS:
            logger.warning(
                "Allowing lead-agent web fallback after government-project subagent attempts failed",
                extra={
                    "tool_name": name,
                    "tool_call_id": str(request.tool_call.get("id") or _MISSING_TOOL_CALL_ID),
                    "terminal_tasks": terminal_tasks,
                },
            )
            return None

        logger.warning(
            "Blocked lead-agent web tool before subagent orchestration for complex government research",
            extra={"tool_name": name, "tool_call_id": str(request.tool_call.get("id") or _MISSING_TOOL_CALL_ID)},
        )
        return self._tool_message(request, _BLOCK_MESSAGE)

    @staticmethod
    def _tool_message(request: ToolCallRequest, content: str) -> ToolMessage:
        name = str(request.tool_call.get("name") or "unknown_tool")
        tool_call_id = str(request.tool_call.get("id") or _MISSING_TOOL_CALL_ID)
        return ToolMessage(content=content, tool_call_id=tool_call_id, name=name, status="error")

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
