#!/usr/bin/env python3
"""Run live Agent Base smoke tests with UTF-8 prompts.

This script avoids piping non-ASCII prompts through PowerShell stdin, which can
transcode Chinese text through the active console code page before Python sees
it. Keep prompts in this UTF-8 source file, or pass ASCII-only overrides.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"


CHINESE_COMPLEX_PROMPT = """\
你是一个资深智能体平台架构师。请分析一个基于 DeerFlow 二次开发的 Agent Base 项目，
从后端运行时、工具系统、subagent 协作、sandbox 安全、CI 交付硬化五个方面给出：
1. 三个最高优先级风险；
2. 每个风险的可验证改进动作；
3. 一个两周内可落地的测试计划。
要求结构清晰，避免泛泛而谈。
"""


SUBAGENT_ORCHESTRATION_PROMPT = """\
You must use the `task` tool exactly two times before writing the final answer.
Delegate both tasks to the `general-purpose` subagent.

Task 1: assess backend runtime and streaming reliability risks for Agent Base.
Task 2: assess sandbox, tool permission, and subagent coordination risks for Agent Base.

After both subagents return, synthesize:
1. what each subagent found;
2. where their findings overlap;
3. one concrete two-week validation plan.

Do not answer from your own analysis alone. The purpose of this run is to verify
parent-agent to subagent scheduling, streaming, and result synthesis.
"""


def configure_utf8_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def configure_environment(args: argparse.Namespace) -> None:
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("AGENT_BASE_PROJECT_ROOT", str(REPO_ROOT))
    os.environ.setdefault("AGENT_BASE_CONFIG_PATH", str(REPO_ROOT / "config.yaml"))
    os.environ.setdefault("AGENT_BASE_HOME", str(REPO_ROOT / ".agent-base" / "live-smoke"))

    if args.api_key_env and args.api_key:
        os.environ[args.api_key_env] = args.api_key


def _preview(data: Any, limit: int = 700) -> str:
    text = repr(data)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def run_chat(args: argparse.Namespace) -> int:
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        model_name=args.model,
        thinking_enabled=False,
        subagent_enabled=False,
        plan_mode=False,
        checkpointer=None,
    )
    result = client.chat(CHINESE_COMPLEX_PROMPT, thread_id="live-smoke-chinese-utf8")
    print("CHAT_OK")
    print(result)
    return 0 if result.strip() else 1


def run_subagent(args: argparse.Namespace) -> int:
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        model_name=args.model,
        thinking_enabled=False,
        subagent_enabled=True,
        plan_mode=False,
        checkpointer=None,
    )

    task_started = 0
    task_completed = 0
    task_failed = 0
    task_running = 0
    task_tool_calls = 0
    ai_chunks: list[str] = []
    final_usage = None

    for event in client.stream(
        SUBAGENT_ORCHESTRATION_PROMPT,
        thread_id="live-smoke-subagent-orchestration",
        subagent_enabled=True,
        max_concurrent_subagents=2,
    ):
        custom_type = event.data.get("type") if event.type == "custom" and isinstance(event.data, dict) else None
        if custom_type == "task_started":
            task_started += 1
            print("TASK_STARTED", _preview(event.data))
        elif custom_type == "task_running":
            task_running += 1
            print("TASK_RUNNING", _preview(event.data))
        elif custom_type == "task_completed":
            task_completed += 1
            print("TASK_COMPLETED", _preview(event.data))
        elif custom_type in {"task_failed", "task_timed_out", "task_cancelled"}:
            task_failed += 1
            print("TASK_TERMINAL_ERROR", custom_type, _preview(event.data))
        elif event.type == "messages-tuple":
            content = event.data.get("content")
            if isinstance(content, str) and content:
                ai_chunks.append(content)
            tool_calls = event.data.get("tool_calls")
            if tool_calls:
                task_tool_calls += sum(1 for tool_call in tool_calls if tool_call.get("name") == "task")
                print("TOOL_CALLS", _preview(tool_calls))
        elif event.type == "end":
            final_usage = event.data.get("usage")

    final_text = "".join(ai_chunks).strip()
    succeeded_mentions = final_text.count("Task Succeeded")
    print("SUBAGENT_SMOKE_SUMMARY")
    print(f"task_tool_calls={task_tool_calls}")
    print(f"task_started={task_started}")
    print(f"task_running={task_running}")
    print(f"task_completed={task_completed}")
    print(f"task_failed={task_failed}")
    print(f"task_succeeded_mentions={succeeded_mentions}")
    print(f"usage={final_usage}")
    print("FINAL_TEXT_PREVIEW")
    print(final_text[:2000])

    observed_subagent_success = task_completed >= 1 or succeeded_mentions >= 1
    if task_tool_calls < 1 or not observed_subagent_success or task_failed:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["chat", "subagent"], default="chat")
    parser.add_argument("--model", default="qwen3.6-plus")
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    configure_utf8_stdio()
    configure_environment(args)

    if args.mode == "chat":
        return run_chat(args)
    return run_subagent(args)


if __name__ == "__main__":
    sys.exit(main())
