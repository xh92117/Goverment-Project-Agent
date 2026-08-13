import { describe, expect, it } from "vitest";

import {
  normalizeAssistantMarkdown,
  normalizeMessages,
  prepareAssistantContent,
  stripEmoji,
} from "@/features/chat/message-utils";

describe("chat page message history normalization", () => {
  it("reads persisted run-event message rows returned by the gateway", () => {
    const messages = normalizeMessages([
      {
        event_type: "llm.human.input",
        category: "message",
        seq: 1,
        content: {
          type: "human",
          id: "human-1",
          content: "你好",
        },
      },
      {
        event_type: "llm.ai.response",
        category: "message",
        seq: 2,
        content: {
          type: "ai",
          id: "ai-1",
          content: "你好，有什么可以帮你？",
        },
      },
    ]);

    expect(messages).toEqual([
      { id: "human-1", role: "user", content: "你好" },
      { id: "ai-1", role: "assistant", content: "你好，有什么可以帮你？" },
    ]);
  });

  it("removes emoji from assistant display text", () => {
    expect(stripEmoji("你好！👋 **重点**：请看这里 🚀")).toBe("你好！ **重点**：请看这里");
  });

  it("normalizes common assistant markdown heading mistakes", () => {
    expect(normalizeAssistantMarkdown("##路基填方施工质量\n\n###一、国内外研究现状")).toBe(
      "## 路基填方施工质量\n\n### 一、国内外研究现状",
    );
  });

  it("extracts assistant citations without leaving knowledge paths in the main text", () => {
    const prepared = prepareAssistantContent(
      "结论来自综合归纳。【知识库：研究现状 | 申报书章节/研究现状.md | 1.3.2】另见 [citation:官方通知](https://example.com/notice)。",
    );

    expect(prepared.content).toBe("结论来自综合归纳。另见 [官方通知](https://example.com/notice)。");
    expect(prepared.citations).toEqual([
      {
        kind: "knowledge",
        title: "研究现状",
        detail: "申报书章节/研究现状.md | 1.3.2",
      },
      {
        kind: "web",
        title: "官方通知",
        href: "https://example.com/notice",
      },
    ]);
  });

  it("drops raw knowledge retrieval payloads from persisted assistant history", () => {
    const payload = JSON.stringify({
      results: [
        {
          entry: {
            index_id: "idx_knowledge",
            file_path: "knowledge/policy.md",
            recommended_sections: [{ heading: "指南", summary: "内部检索摘要" }],
          },
        },
      ],
    });

    expect(
      normalizeMessages([
        {
          type: "ai",
          id: "ai-knowledge",
          content: payload,
        },
      ]),
    ).toEqual([]);
  });
});
