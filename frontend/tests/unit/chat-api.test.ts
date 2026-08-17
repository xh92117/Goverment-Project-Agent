import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createThread,
  downloadThreadArtifact,
  extractMessageContent,
  extractStreamActions,
  GOVERNMENT_PROJECT_ASSISTANT_ID,
  isRawKnowledgePayload,
  listThreadArtifacts,
  normalizeExecutionMode,
  withGovernmentProjectRuntimeContext,
} from "@/features/chat/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat api stream message parsing", () => {
  it("normalizes execution modes for run context", () => {
    expect(normalizeExecutionMode("deep")).toBe("deep");
    expect(normalizeExecutionMode("standard")).toBe("standard");
    expect(normalizeExecutionMode("unknown")).toBe("standard");
  });

  it("always advertises web search for government-project runs", () => {
    expect(
      withGovernmentProjectRuntimeContext({
        project_id: "project-1",
        government_project_tools: { knowledge: false, web: false },
        government_project_capabilities: { webSearch: false },
      }),
    ).toMatchObject({
      project_id: "project-1",
      government_project_tools: { knowledge: false, plan: true, web: true },
      government_project_capabilities: { knowledgeRag: true, webSearch: true },
    });
  });

  it("extracts AI text chunks from LangGraph message tuples", () => {
    expect(
      extractMessageContent([{ type: "AIMessageChunk", content: "hello" }, {}]),
    ).toBe("hello");
  });

  it("extracts AI text chunks from nested LangChain message dumps", () => {
    expect(
      extractMessageContent([
        {
          type: "constructor",
          id: ["langchain", "schema", "messages", "AIMessageChunk"],
          kwargs: { content: "hello" },
        },
        {},
      ]),
    ).toBe("hello");
  });

  it("filters human and tool messages from streamed output", () => {
    expect(
      extractMessageContent([{ type: "HumanMessage", content: "prompt" }, {}]),
    ).toBeNull();
    expect(
      extractMessageContent([
        { type: "ToolMessage", content: "tool result" },
        {},
      ]),
    ).toBeNull();
  });

  it("ignores empty AI tool-call planning messages", () => {
    expect(
      extractMessageContent([{ type: "AIMessageChunk", content: "" }, {}]),
    ).toBeNull();
  });

  it("ignores malformed message types instead of stringifying objects", () => {
    expect(
      extractMessageContent([
        { type: { role: "AIMessageChunk" }, content: "hidden" },
        {},
      ]),
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
    expect(
      extractMessageContent([{ type: "AIMessageChunk", content: payload }, {}]),
    ).toBeNull();
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
            tool_call_chunks: [
              { id: "call-partial", type: "tool_call", args: "{}" },
            ],
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
          message:
            "Recursion limit of 100 reached without hitting a stop condition.",
        },
        "error",
      ),
    ).toEqual([
      {
        id: "status:GraphRecursionError:Recursion limit of 100 reached without hitting a",
        kind: "status",
        status: "error",
        title: "运行失败",
        detail:
          "Recursion limit of 100 reached without hitting a stop condition.",
      },
    ]);
  });

  it("creates chat threads against the government declaration assistant", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ thread_id: "thread-1", status: "idle" }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await createThread("thread-1", { title: "test" });

    const body = JSON.parse(
      String(fetchMock.mock.calls[0]?.[1]?.body),
    ) as Record<string, unknown>;
    expect(body.assistant_id).toBe(GOVERNMENT_PROJECT_ASSISTANT_ID);
  });

  it("lists and downloads the current thread artifacts", async () => {
    const artifact = {
      name: "国内外研究现状.md",
      path: "/mnt/user-data/outputs/国内外研究现状.md",
      relative_path: "国内外研究现状.md",
      size: 128,
      updated_at: "2026-08-17T00:00:00+00:00",
      mime_type: "text/markdown",
      download_url:
        "/api/threads/thread-1/artifacts/mnt/user-data/outputs/%E5%9B%BD%E5%86%85%E5%A4%96%E7%A0%94%E7%A9%B6%E7%8E%B0%E7%8A%B6.md?download=true",
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({
          thread_id: "thread-1",
          artifacts: [artifact],
          total: 1,
          truncated: false,
        }),
      )
      .mockResolvedValueOnce(new Response(new Blob(["# 研究现状"])));
    vi.stubGlobal("fetch", fetchMock);

    const listed = await listThreadArtifacts("thread-1");
    const downloaded = await downloadThreadArtifact(
      listed.artifacts[0]!.download_url,
    );

    expect(listed.artifacts[0]?.name).toBe("国内外研究现状.md");
    expect(await downloaded.text()).toBe("# 研究现状");
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/threads/thread-1/artifacts",
      expect.objectContaining({ credentials: "include" }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      artifact.download_url,
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("renders a refreshable downloadable artifact panel in standalone chat", () => {
    const pageSource = readFileSync(
      new URL("../../src/features/chat/chat-page.tsx", import.meta.url),
      "utf8",
    );

    expect(pageSource).toContain('id="chat-artifacts-panel"');
    expect(pageSource).toContain("listThreadArtifacts(threadId)");
    expect(pageSource).toContain("refetchInterval: isRunning ? 2_000 : false");
    expect(pageSource).toContain("downloadArtifact.mutate(artifact)");
    expect(pageSource).toContain("智能体运行中，产物列表会自动更新");
  });

  it("does not expose thread IDs or selected model names in chat headers", () => {
    const standaloneSource = readFileSync(
      new URL("../../src/features/chat/chat-page.tsx", import.meta.url),
      "utf8",
    );
    const projectSource = readFileSync(
      new URL(
        "../../src/features/projects/project-workspace-page.tsx",
        import.meta.url,
      ),
      "utf8",
    );
    const standaloneHeader = standaloneSource.slice(
      standaloneSource.indexOf('<header className="main-head">'),
      standaloneSource.indexOf("</header>"),
    );
    const projectHeader = projectSource.slice(
      projectSource.indexOf('<header className="main-head">'),
      projectSource.indexOf("</header>"),
    );

    expect(standaloneHeader).not.toContain("threadId.slice");
    expect(standaloneHeader).not.toContain("selectedModel");
    expect(standaloneHeader).not.toContain('className="tag muted"');
    expect(projectHeader).not.toContain("threadId");
    expect(projectHeader).not.toContain("selectedModel");
    expect(projectHeader).not.toContain('className="tag muted"');
  });
});
