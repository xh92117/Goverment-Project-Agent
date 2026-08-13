#!/usr/bin/env python3
"""Run a live government-project search task through subagents.

This is a runnable smoke check for the actual Agent Base runtime:
- parent agent is created with subagent delegation enabled;
- the prompt requires two `task` subagents;
- each subagent prompt requires `web_search` first and `web_fetch` where useful;
- stream events and the final answer are written to stdout for background logs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
HARNESS_DIR = BACKEND_DIR / "packages" / "harness"
if str(HARNESS_DIR) not in sys.path:
    sys.path.insert(0, str(HARNESS_DIR))


PROMPT = """\
请以政府科研项目申报助手身份回答：查找“动态回弹模型检测技术现状”。

硬性执行要求：
1. 在给出最终答案前，必须先启动 2 个 `task` 子智能体：A 使用 `literature-researcher`，B 使用 `standards-patent-researcher`。
2. 子智能体 A 的任务：检索并归纳“动态回弹模型/动态回弹模量”的文献与技术现状，必须先调用 `web_search`，必要时调用 `web_fetch`；最多 2 次 `web_search`、最多 3 次 `web_fetch`。
3. 子智能体 B 的任务：检索并归纳该方向的检测方法、标准规程、专利与工程应用，必须先调用 `web_search`，必要时调用 `web_fetch`；最多 2 次 `web_search`、最多 3 次 `web_fetch`。
4. 父智能体只负责综合两个子智能体的结果，不要跳过子智能体直接作答。

最终答案请用中文，结构包括：
- 一句话总体判断
- 技术现状
- 主流检测/测试方法
- 代表性文献、标准、专利或公开资料
- 主要问题与发展趋势
- 参考来源链接
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
    from deerflow.government_project_workspace import resolve_government_project_paths

    load_dotenv(REPO_ROOT / ".env", override=False)
    paths = resolve_government_project_paths(allow_runtime_inside_source=False)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("AGENT_BASE_PROJECT_ROOT", str(REPO_ROOT))
    os.environ.setdefault("AGENT_BASE_CONFIG_PATH", str(REPO_ROOT / "config.yaml"))
    os.environ.setdefault("GP_AGENT_HOME", str(paths.gp_agent_home))
    os.environ.setdefault("AGENT_BASE_HOME", str(args.runtime_home or paths.runtime_home))
    os.environ.setdefault("DEER_FLOW_HOME", os.environ["AGENT_BASE_HOME"])
    os.environ.setdefault("AGENT_BASE_HOST_BASE_DIR", os.environ["AGENT_BASE_HOME"])
    os.environ.setdefault("GOVERNMENT_PROJECT_WORKSPACE_ROOT", str(paths.workspace_root))
    os.environ.setdefault("AGENT_BASE_KNOWLEDGE_ROOT", str(paths.knowledge_root))
    os.environ.setdefault("GOVERNMENT_PROJECT_DRAFTS_ROOT", str(paths.drafts_root))
    os.environ.setdefault("GOVERNMENT_PROJECT_PROJECTS_ROOT", str(paths.projects_root))
    os.environ.setdefault("GOVERNMENT_PROJECT_LOG_ROOT", str(paths.logs_root))
    os.environ.setdefault("AGENT_BASE_DB_PATH", str(Path(os.environ["AGENT_BASE_HOME"]) / "data" / "agent_base.db"))

    python_paths = [str(BACKEND_DIR), str(BACKEND_DIR / "packages" / "harness")]
    if os.environ.get("PYTHONPATH"):
        python_paths.append(os.environ["PYTHONPATH"])
    os.environ["PYTHONPATH"] = os.pathsep.join(python_paths)


def _preview(data: Any, limit: int = 1200) -> str:
    if isinstance(data, str):
        text = data
    else:
        text = repr(data)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _json_line(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True)


def run(args: argparse.Namespace) -> int:
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient(
        model_name=args.model,
        thinking_enabled=False,
        subagent_enabled=True,
        plan_mode=False,
        checkpointer=None,
        agent_name=args.agent_name,
    )

    counters = {
        "task_tool_calls": 0,
        "web_search_tool_calls": 0,
        "web_fetch_tool_calls": 0,
        "task_started": 0,
        "task_completed": 0,
        "task_failed": 0,
        "tool_results_task": 0,
        "tool_results_web_search": 0,
        "tool_results_web_fetch": 0,
    }
    ai_chunks: list[str] = []
    final_usage: dict[str, Any] | None = None

    _json_line(
        "run_started",
        model=args.model,
        agent_name=args.agent_name,
        thread_id=args.thread_id,
        runtime_home=str(args.runtime_home),
    )

    for event in client.stream(
        PROMPT,
        thread_id=args.thread_id,
        subagent_enabled=True,
        max_concurrent_subagents=2,
        recursion_limit=args.recursion_limit,
    ):
        if event.type == "custom" and isinstance(event.data, dict):
            custom_type = event.data.get("type")
            if custom_type == "task_started":
                counters["task_started"] += 1
                _json_line("task_started", data=_preview(event.data))
            elif custom_type == "task_completed":
                counters["task_completed"] += 1
                _json_line("task_completed", data=_preview(event.data))
            elif custom_type in {"task_failed", "task_timed_out", "task_cancelled"}:
                counters["task_failed"] += 1
                _json_line("task_terminal_error", custom_type=custom_type, data=_preview(event.data))
            continue

        if event.type == "messages-tuple" and isinstance(event.data, dict):
            content = event.data.get("content")
            if isinstance(content, str) and content and event.data.get("type") == "ai":
                ai_chunks.append(content)

            tool_calls = event.data.get("tool_calls")
            if tool_calls:
                names = [tool_call.get("name") for tool_call in tool_calls if isinstance(tool_call, dict)]
                counters["task_tool_calls"] += names.count("task")
                counters["web_search_tool_calls"] += names.count("web_search")
                counters["web_fetch_tool_calls"] += names.count("web_fetch")
                _json_line("tool_calls", names=names, calls=_preview(tool_calls))

            if event.data.get("type") == "tool":
                name = event.data.get("name")
                if name == "task":
                    counters["tool_results_task"] += 1
                elif name == "web_search":
                    counters["tool_results_web_search"] += 1
                elif name == "web_fetch":
                    counters["tool_results_web_fetch"] += 1
                if name in {"task", "web_search", "web_fetch"}:
                    _json_line("tool_result", name=name, content=_preview(event.data.get("content"), limit=1800))

        elif event.type == "end" and isinstance(event.data, dict):
            final_usage = event.data.get("usage")

    final_text = "".join(ai_chunks).strip()
    _json_line("run_summary", counters=counters, usage=final_usage)
    print("FINAL_ANSWER_BEGIN", flush=True)
    print(final_text, flush=True)
    print("FINAL_ANSWER_END", flush=True)

    if counters["task_tool_calls"] < 2 or counters["task_completed"] < 1 or counters["task_failed"]:
        return 1
    return 0 if final_text else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--agent-name", default="government-project-declaration")
    parser.add_argument("--thread-id", default="gov_search_dynamic_resilient_modulus_subagent_smoke")
    parser.add_argument("--runtime-home", type=Path, default=None)
    parser.add_argument("--recursion-limit", type=int, default=120)
    args = parser.parse_args()

    configure_utf8_stdio()
    configure_environment(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
