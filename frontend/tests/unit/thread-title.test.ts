import { describe, expect, it } from "vitest";

import {
  summarizeThreadTitle,
  UNTITLED_DIRECT_THREAD_TITLE,
} from "@/features/chat/thread-title";

describe("thread title summary", () => {
  it("derives a compact title from the first user prompt", () => {
    expect(summarizeThreadTitle("请帮我检索并总结当前项目相关的申报政策指南，重点列出申报条件。")).toBe(
      "检索并总结当前项目相关的申报政策指南",
    );
  });

  it("falls back only when the prompt is empty", () => {
    expect(summarizeThreadTitle("   ")).toBe(UNTITLED_DIRECT_THREAD_TITLE);
  });
});
