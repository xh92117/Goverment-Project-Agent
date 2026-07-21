from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from deerflow.agents.middlewares.tool_call_budget_middleware import ToolCallBudgetMiddleware


def _request(tool_name: str, call_id: str, messages: list) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_name, "id": call_id, "args": {"query": "test"}},
        tool=None,
        state={"messages": messages},
        runtime=MagicMock(),
    )


def test_allows_calls_through_configured_limit():
    middleware = ToolCallBudgetMiddleware({"web_search": 2})
    messages = [HumanMessage(content="research")]
    request = _request("web_search", "search-1", messages)
    expected = ToolMessage(content="ok", tool_call_id="search-1", name="web_search")

    assert middleware.wrap_tool_call(request, lambda _request: expected) is expected


def test_blocks_sequential_call_above_limit():
    middleware = ToolCallBudgetMiddleware({"web_search": 2})
    messages = [
        HumanMessage(content="research"),
        ToolMessage(content="one", tool_call_id="search-1", name="web_search"),
        ToolMessage(content="two", tool_call_id="search-2", name="web_search"),
    ]
    handler = MagicMock()

    result = middleware.wrap_tool_call(_request("web_search", "search-3", messages), handler)

    assert result.status == "error"
    assert "Hard limit: 2" in str(result.content)
    handler.assert_not_called()


def test_blocks_parallel_call_above_limit_in_same_ai_message():
    middleware = ToolCallBudgetMiddleware({"web_fetch": 2})
    calls = [
        {"name": "web_fetch", "id": "fetch-1", "args": {"url": "https://a.example"}},
        {"name": "web_fetch", "id": "fetch-2", "args": {"url": "https://b.example"}},
        {"name": "web_fetch", "id": "fetch-3", "args": {"url": "https://c.example"}},
    ]
    messages = [HumanMessage(content="research"), AIMessage(content="", tool_calls=calls)]

    first = middleware.wrap_tool_call(_request("web_fetch", "fetch-1", messages), lambda _request: ToolMessage(content="ok", tool_call_id="fetch-1", name="web_fetch"))
    third_handler = MagicMock()
    third = middleware.wrap_tool_call(_request("web_fetch", "fetch-3", messages), third_handler)

    assert first.status != "error"
    assert third.status == "error"
    assert "blocked attempt: 3" in str(third.content)
    third_handler.assert_not_called()


def test_unconfigured_tool_is_not_limited():
    middleware = ToolCallBudgetMiddleware({"web_search": 1})
    request = _request("knowledge_search_index", "knowledge-1", [])
    expected = ToolMessage(content="ok", tool_call_id="knowledge-1", name="knowledge_search_index")

    assert middleware.wrap_tool_call(request, lambda _request: expected) is expected


@pytest.mark.asyncio
async def test_async_path_blocks_without_calling_handler():
    middleware = ToolCallBudgetMiddleware({"web_extract": 1})
    messages = [ToolMessage(content="one", tool_call_id="extract-1", name="web_extract")]
    handler = AsyncMock()

    result = await middleware.awrap_tool_call(_request("web_extract", "extract-2", messages), handler)

    assert result.status == "error"
    handler.assert_not_awaited()
