from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from deerflow.agents.middlewares.government_research_orchestration_middleware import (
    GovernmentResearchOrchestrationMiddleware,
)


def _request(tool_name: str, messages: list, call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_name, "id": call_id, "args": {"query": "test"}},
        tool=None,
        state={"messages": messages},
        runtime=MagicMock(),
    )


def test_blocks_lead_web_search_before_task_for_complex_research():
    middleware = GovernmentResearchOrchestrationMiddleware()
    request = _request("web_search", [HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状")])
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "web_search"
    assert "并行发起 2-3 个 `task` 调用" in str(result.content)
    handler.assert_not_called()


def test_blocks_lead_web_search_for_declaration_basis_wording():
    middleware = GovernmentResearchOrchestrationMiddleware()
    request = _request("web_search", [HumanMessage(content="帮我分析这个课题的申报依据和竞争力")])
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.name == "web_search"
    handler.assert_not_called()


def test_allows_web_search_after_task_result_for_complex_research():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(
            content="Task Succeeded. Result: ok",
            tool_call_id="task-1",
            name="task",
            additional_kwargs={"subagent_status": "completed"},
        ),
    ]
    request = _request("web_search", messages)
    expected = ToolMessage(content="ok", tool_call_id="call-1", name="web_search")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected


def test_allows_web_search_after_task_result_using_text_status_fallback():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(content="Task Succeeded. Result: ok", tool_call_id="task-1", name="task"),
    ]
    request = _request("web_search", messages)
    expected = ToolMessage(content="ok", tool_call_id="call-1", name="web_search")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected


def test_blocks_web_search_after_failed_task_for_complex_research():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(
            content="Task failed. Error: recursion limit",
            tool_call_id="task-1",
            name="task",
            additional_kwargs={"subagent_status": "failed"},
        ),
    ]
    request = _request("web_search", messages)
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()


def test_allows_web_search_fallback_after_two_failed_tasks_for_complex_research():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状")]
    messages.extend(
        ToolMessage(
            content="Task failed. Error: recursion limit",
            tool_call_id=f"task-{index}",
            name="task",
            additional_kwargs={"subagent_status": "failed"},
        )
        for index in range(2)
    )
    request = _request("web_search", messages)
    expected = ToolMessage(content="ok", tool_call_id="call-1", name="web_search")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected


def test_blocks_more_task_calls_after_successful_task_using_text_status_fallback():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(content="Task Succeeded. Result: ok", tool_call_id="task-1", name="task"),
    ]
    request = _request("task", messages)
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    handler.assert_not_called()


def test_allows_one_supplemental_task_after_partial_subagent_success():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(
            content="Task Succeeded. Result: ok",
            tool_call_id="task-1",
            name="task",
            additional_kwargs={"subagent_status": "completed"},
        ),
        ToolMessage(
            content="Task failed. Error: recursion limit",
            tool_call_id="task-2",
            name="task",
            additional_kwargs={"subagent_status": "failed"},
        ),
    ]
    request = _request("task", messages)
    expected = ToolMessage(content="Task Succeeded. Result: gap filled", tool_call_id="call-1", name="task")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected


def test_blocks_more_task_calls_after_successful_task_for_complex_research():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [
        HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状"),
        ToolMessage(
            content="Task Succeeded. Result: ok",
            tool_call_id="task-1",
            name="task",
            additional_kwargs={"subagent_status": "completed"},
        ),
    ]
    request = _request("task", messages)
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "不要在同一用户轮次继续发起 `task` 调用" in str(result.content)
    handler.assert_not_called()


def test_blocks_more_task_calls_after_three_failed_attempts():
    middleware = GovernmentResearchOrchestrationMiddleware()
    messages = [HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状")]
    messages.extend(
        ToolMessage(
            content="Task failed. Error: recursion limit",
            tool_call_id=f"task-{index}",
            name="task",
            additional_kwargs={"subagent_status": "failed"},
        )
        for index in range(3)
    )
    request = _request("task", messages)
    handler = MagicMock()

    result = middleware.wrap_tool_call(request, handler)

    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "尝试预算已经用尽" in str(result.content)
    handler.assert_not_called()


def test_allows_simple_lookup_without_task():
    middleware = GovernmentResearchOrchestrationMiddleware()
    request = _request("web_search", [HumanMessage(content="只查这个政策的官网链接")])
    expected = ToolMessage(content="ok", tool_call_id="call-1", name="web_search")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected


def test_does_not_block_task_tool():
    middleware = GovernmentResearchOrchestrationMiddleware()
    request = _request("task", [HumanMessage(content="查看路基填方施工质量现场检测技术的研究现状")])
    expected = ToolMessage(content="Task Succeeded. Result: ok", tool_call_id="call-1", name="task")

    result = middleware.wrap_tool_call(request, lambda _req: expected)

    assert result is expected
