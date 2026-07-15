"""Core behavior tests for TitleMiddleware."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from deerflow.agents.middlewares import title_middleware as title_middleware_module
from deerflow.agents.middlewares.dynamic_context_middleware import _DYNAMIC_CONTEXT_REMINDER_KEY
from deerflow.agents.middlewares.title_middleware import TitleMiddleware
from deerflow.config.title_config import TitleConfig, get_title_config, set_title_config


def _clone_title_config(config: TitleConfig) -> TitleConfig:
    # Avoid mutating shared global config objects across tests.
    return TitleConfig(**config.model_dump())


def _set_test_title_config(**overrides) -> TitleConfig:
    config = _clone_title_config(get_title_config())
    for key, value in overrides.items():
        setattr(config, key, value)
    set_title_config(config)
    return config


class TestTitleMiddlewareCoreLogic:
    def setup_method(self):
        # Title config is a global singleton; snapshot and restore for test isolation.
        self._original = _clone_title_config(get_title_config())

    def teardown_method(self):
        set_title_config(self._original)

    def test_should_generate_title_for_first_complete_exchange(self):
        _set_test_title_config(enabled=True)
        middleware = TitleMiddleware()
        state = {
            "messages": [
                HumanMessage(content="Summarize this code"),
                AIMessage(content="I will inspect the structure first"),
            ]
        }

        assert middleware._should_generate_title(state) is True

    def test_should_generate_title_with_dynamic_context_reminder(self):
        _set_test_title_config(enabled=True)
        middleware = TitleMiddleware()
        state = {
            "messages": [
                HumanMessage(
                    content="<system-reminder>\n<memory>User prefers Python.</memory>\n</system-reminder>",
                    additional_kwargs={_DYNAMIC_CONTEXT_REMINDER_KEY: True},
                ),
                HumanMessage(content="Summarize this code"),
                AIMessage(content="I will inspect the structure first"),
            ]
        }

        assert middleware._should_generate_title(state) is True

    def test_should_not_generate_title_when_disabled_or_already_set(self):
        middleware = TitleMiddleware()

        _set_test_title_config(enabled=False)
        disabled_state = {
            "messages": [HumanMessage(content="Q"), AIMessage(content="A")],
            "title": None,
        }
        assert middleware._should_generate_title(disabled_state) is False

        _set_test_title_config(enabled=True)
        titled_state = {
            "messages": [HumanMessage(content="Q"), AIMessage(content="A")],
            "title": "Existing Title",
        }
        assert middleware._should_generate_title(titled_state) is False

    def test_should_not_generate_title_after_second_user_turn(self):
        _set_test_title_config(enabled=True)
        middleware = TitleMiddleware()
        state = {
            "messages": [
                HumanMessage(content="First question"),
                AIMessage(content="First answer"),
                HumanMessage(content="Second question"),
                AIMessage(content="Second answer"),
            ]
        }

        assert middleware._should_generate_title(state) is False

    def test_generate_title_uses_async_model_and_respects_max_chars(self, monkeypatch):
        _set_test_title_config(max_chars=12, model_name=None)
        middleware = TitleMiddleware()
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Short title"))
        monkeypatch.setattr(title_middleware_module, "create_chat_model", MagicMock(return_value=model))

        state = {
            "messages": [
                HumanMessage(content="Please write a very long script title"),
                AIMessage(content="Sure, I will confirm the requirements first"),
            ]
        }
        result = asyncio.run(middleware._agenerate_title_result(state))
        title = result["title"]

        assert title == "Short title"
        title_middleware_module.create_chat_model.assert_called_once_with(thinking_enabled=False, attach_tracing=False)
        model.ainvoke.assert_awaited_once()
        assert model.ainvoke.await_args.kwargs["config"] == {
            "run_name": "title_agent",
            "tags": ["middleware:title"],
        }

    def test_generate_title_uses_explicit_app_config_without_global_config(self, monkeypatch):
        title_config = TitleConfig(enabled=True, model_name="title-model", max_chars=20)
        app_config = SimpleNamespace(title=title_config)
        middleware = TitleMiddleware(app_config=app_config)
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Explicit title"))

        def fail_get_title_config():
            raise AssertionError("ambient get_title_config() must not be used when app_config is explicit")

        monkeypatch.setattr(title_middleware_module, "get_title_config", fail_get_title_config)
        monkeypatch.setattr(title_middleware_module, "create_chat_model", MagicMock(return_value=model))

        state = {
            "messages": [
                HumanMessage(content="Please write a title"),
                AIMessage(content="Sure"),
            ]
        }
        result = asyncio.run(middleware._agenerate_title_result(state))

        assert result == {"title": "Explicit title"}
        title_middleware_module.create_chat_model.assert_called_once_with(
            name="title-model",
            thinking_enabled=False,
            attach_tracing=False,
            app_config=app_config,
        )

    def test_generate_title_normalizes_structured_message_content(self, monkeypatch):
        _set_test_title_config(max_chars=20)
        middleware = TitleMiddleware()
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="Summarize code"))
        monkeypatch.setattr(title_middleware_module, "create_chat_model", MagicMock(return_value=model))

        state = {
            "messages": [
                HumanMessage(content=[{"type": "text", "text": "Summarize this code"}]),
                AIMessage(content=[{"type": "text", "text": "Sure, I will inspect it"}]),
            ]
        }

        result = asyncio.run(middleware._agenerate_title_result(state))
        title = result["title"]

        assert title == "Summarize code"

    def test_generate_title_fallback_for_long_message(self, monkeypatch):
        _set_test_title_config(max_chars=20)
        middleware = TitleMiddleware()
        model = MagicMock()
        model.ainvoke = AsyncMock(side_effect=RuntimeError("model unavailable"))
        monkeypatch.setattr(title_middleware_module, "create_chat_model", MagicMock(return_value=model))

        state = {
            "messages": [
                HumanMessage(content="This is a very long question description that needs a fallback title"),
                AIMessage(content="Received"),
            ]
        }
        result = asyncio.run(middleware._agenerate_title_result(state))
        title = result["title"]

        # Assert behavior (truncated fallback + ellipsis) without overfitting exact text.
        assert title.endswith("...")
        assert title.startswith("This is a very long")

    def test_aafter_model_delegates_to_async_helper(self, monkeypatch):
        middleware = TitleMiddleware()

        monkeypatch.setattr(middleware, "_agenerate_title_result", AsyncMock(return_value={"title": "Async title"}))
        result = asyncio.run(middleware.aafter_model({"messages": []}, runtime=MagicMock()))
        assert result == {"title": "Async title"}

        monkeypatch.setattr(middleware, "_agenerate_title_result", AsyncMock(return_value=None))
        assert asyncio.run(middleware.aafter_model({"messages": []}, runtime=MagicMock())) is None

    def test_after_model_sync_delegates_to_sync_helper(self, monkeypatch):
        middleware = TitleMiddleware()

        monkeypatch.setattr(middleware, "_generate_title_result", MagicMock(return_value={"title": "Sync title"}))
        result = middleware.after_model({"messages": []}, runtime=MagicMock())
        assert result == {"title": "Sync title"}

        monkeypatch.setattr(middleware, "_generate_title_result", MagicMock(return_value=None))
        assert middleware.after_model({"messages": []}, runtime=MagicMock()) is None

    def test_sync_generate_title_uses_fallback_without_model(self):
        """Sync path avoids LLM calls and derives a local fallback title."""
        _set_test_title_config(max_chars=20)
        middleware = TitleMiddleware()

        state = {
            "messages": [
                HumanMessage(content="Please write tests"),
                AIMessage(content="Sure"),
            ]
        }
        result = middleware._generate_title_result(state)
        assert result == {"title": "Please write tests"}

    def test_sync_generate_title_respects_fallback_truncation(self):
        """Sync fallback path still respects max_chars truncation rules."""
        _set_test_title_config(max_chars=50)
        middleware = TitleMiddleware()

        state = {
            "messages": [
                HumanMessage(
                    content=(
                        "This is a very long question description that needs to be truncated "
                        "into a fallback title with extra context beyond the local limit"
                    )
                ),
                AIMessage(content="Reply"),
            ]
        }
        result = middleware._generate_title_result(state)
        assert result["title"].endswith("...")
        assert result["title"].startswith("This is a very long question description")

    def test_parse_title_strips_think_tags(self):
        """Title model responses with <think>...</think> blocks are stripped before use."""
        middleware = TitleMiddleware()
        raw = "<think>The user wants a report. I should use a documentation skill.</think>City development report"
        result = middleware._parse_title(raw)
        assert "<think>" not in result
        assert result == "City development report"

    def test_parse_title_strips_think_tags_only_response(self):
        """If model only outputs a think block and nothing else, title is empty string."""
        middleware = TitleMiddleware()
        raw = "<think>just thinking, no real title</think>"
        result = middleware._parse_title(raw)
        assert result == ""

    def test_build_title_prompt_strips_assistant_think_tags(self):
        """<think> blocks in assistant messages are stripped before being included in the title prompt."""
        _set_test_title_config(enabled=True)
        middleware = TitleMiddleware()
        state = {
            "messages": [
                HumanMessage(content="Research city development"),
                AIMessage(content="<think>Analyze the request</think>I will research the city's development."),
            ]
        }
        prompt, _ = middleware._build_title_prompt(state)
        assert "<think>" not in prompt

    def test_build_title_prompt_uses_real_user_message_with_dynamic_context_reminder(self):
        _set_test_title_config(enabled=True)
        middleware = TitleMiddleware()
        state = {
            "messages": [
                HumanMessage(
                    content="<system-reminder>\n<memory>User prefers Python.</memory>\n</system-reminder>",
                    additional_kwargs={_DYNAMIC_CONTEXT_REMINDER_KEY: True},
                ),
                HumanMessage(content="Please write tests"),
                AIMessage(content="Sure"),
            ]
        }

        prompt, user_msg = middleware._build_title_prompt(state)
        assert user_msg == "Please write tests"
        assert "<system-reminder>" not in prompt
        assert "User prefers Python" not in prompt

    def test_generate_title_async_strips_think_tags_in_response(self, monkeypatch):
        """Async title generation strips <think> blocks from the model response."""
        _set_test_title_config(max_chars=50)
        middleware = TitleMiddleware()
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=AIMessage(content="<think>User wants research.</think>City research"))
        monkeypatch.setattr(title_middleware_module, "create_chat_model", MagicMock(return_value=model))

        state = {
            "messages": [
                HumanMessage(content="Please research the last five years of city development"),
                AIMessage(content="Sure"),
            ]
        }
        result = asyncio.run(middleware._agenerate_title_result(state))
        assert result is not None
        assert "<think>" not in result["title"]
        assert result["title"] == "City research"
