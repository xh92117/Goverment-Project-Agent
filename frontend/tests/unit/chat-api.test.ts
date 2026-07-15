import { describe, expect, it, vi } from "vitest";

import {
  createThread,
  extractMessageContent,
  extractStreamActions,
  GOVERNMENT_PROJECT_ASSISTANT_ID,
  isRawKnowledgePayload,
  normalizeExecutionMode,
} from "@/features/chat/api";

describe("chat api stream message parsing", () => {
  it("normalizes execution modes for run context", () => {
    expect(normalizeExecutionMode("deep")).toBe("deep");
    expect(normalizeExecutionMode("standard")).toBe("standard");
    expect(normalizeExecutionMode("unknown")).toBe("standard");
  });

  it("extracts AI text chunks from LangGraph message tuples", () => {
    expect(extractMessageContent([{ type: "AIMessageChunk", content: "hello" }, {}])).toBe(
      "hello",
    );
  });

  it("extracts AI text chunks from nested LangChain message dumps", () => {
    expect(
      extractMessageContent([
        { type: "constructor", id: ["langchain", "schema", "messages", "AIMessageChunk"], kwargs: { content: "hello" } },
        {},
      ]),
    ).toBe("hello");
  });

  it("filters human and tool messages from streamed output", () => {
    expect(extractMessageContent([{ type: "HumanMessage", content: "prompt" }, {}])).toBeNull();
    expect(extractMessageContent([{ type: "ToolMessage", content: "tool result" }, {}])).toBeNull();
  });

  it("ignores empty AI tool-call planning messages", () => {
    expect(extractMessageContent([{ type: "AIMessageChunk", content: "" }, {}])).toBeNull();
  });

  it("ignores malformed message types instead of stringifying objects", () => {
    expect(
      extractMessageContent([{ type: { role: "AIMessageChunk" }, content: "hidden" }, {}]),
    ).toBeNull();
  });

  it("filters raw knowledge retrieval payloads from streamed assistant text", () => {
    const payload = JSON.stringify({
      results: [
        {
          entry: {
            index_id: "idx_1",
            title: "knowledge.md",
            file_path: "knowledge/knowledge.md",
            recommended_sections: [],
          },
        },
      ],
    });

    expect(isRawKnowledgePayload(payload)).toBe(true);
    expect(extractMessageContent([{ type: "AIMessageChunk", content: payload }, {}])).toBeNull();
  });

  it("extracts visible tool-call actions from streamed AI chunks", () => {
    expect(
      extractStreamActions(
        [
          {
            type: "AIMessageChunk",
            content: "",
            tool_calls: [
              {
                id: "call-search",
                name: "web_search",
                args: { query: "2026 国家自然科学基金 面上项目 指南" },
              },
            ],
          },
          {},
        ],
        "messages",
      ),
    ).toEqual([
      {
        id: "tool:call-search",
        kind: "tool",
        status: "running",
        toolName: "web_search",
        title: "正在检索网页",
        detail: "关键词：2026 国家自然科学基金 面上项目 指南",
      },
    ]);
  });

  it("extracts completed tool actions from streamed tool messages", () => {
    expect(
      extractStreamActions(
        [
          {
            type: "ToolMessage",
            name: "web_fetch",
            tool_call_id: "call-fetch",
            content: "页面正文",
          },
          {},
        ],
        "messages",
      ),
    ).toEqual([
      {
        id: "tool:call-fetch",
        kind: "tool",
        status: "completed",
        toolName: "web_fetch",
        title: "读取网页完成",
        detail: "已读取网页内容",
      },
    ]);
  });

  it("ignores unnamed low-level tool call chunks", () => {
    expect(
      extractStreamActions(
        [
          {
            type: "AIMessageChunk",
            content: "",
            tool_call_chunks: [{ id: "call-partial", type: "tool_call", args: "{}" }],
          },
          {},
        ],
        "messages",
      ),
    ).toEqual([]);
  });

  it("extracts run error events as visible status actions", () => {
    expect(
      extractStreamActions(
        {
          name: "GraphRecursionError",
          message: "Recursion limit of 100 reached without hitting a stop condition.",
        },
        "error",
      ),
    ).toEqual([
      {
        id: "status:GraphRecursionError:Recursion limit of 100 reached without hitting a",
        kind: "status",
        status: "error",
        title: "运行失败",
        detail: "Recursion limit of 100 reached without hitting a stop condition.",
      },
    ]);
  });

  it("creates chat threads against the government declaration assistant", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ thread_id: "thread-1", status: "idle" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createThread("thread-1", { title: "test" });

    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as Record<string, unknown>;
    expect(body.assistant_id).toBe(GOVERNMENT_PROJECT_ASSISTANT_ID);
  });
});
