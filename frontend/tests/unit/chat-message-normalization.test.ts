import { describe, expect, it } from "vitest";

import { normalizeMessages } from "@/features/chat/message-utils";

describe("normalizeMessages", () => {
  it("keeps chat messages and hides tool payloads from history", () => {
    const messages = normalizeMessages({
      messages: [
        { type: "human", content: "帮我检索指南", seq: 1 },
        { type: "tool", content: "Knowledge index search found 10 records", seq: 2 },
        { type: "ai", content: "已为你整理政策要点。", seq: 3 },
        {
          type: "ai",
          content:
            '{"results":[{"entry":{"index_id":"idx_1","file_path":"guide.docx","summary":"raw"}}]}',
          seq: 4,
        },
      ],
    });

    expect(messages).toEqual([
      { id: "seq-1", role: "user", content: "帮我检索指南" },
      { id: "seq-3", role: "assistant", content: "已为你整理政策要点。" },
    ]);
  });
});
