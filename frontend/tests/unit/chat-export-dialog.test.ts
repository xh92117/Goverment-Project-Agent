import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it, vi } from "vitest";

import { exportConversationDocx } from "@/features/chat/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat conversation Word export", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/chat/chat-page.tsx", import.meta.url),
    "utf8",
  );

  it("opens a Word settings dialog before exporting", () => {
    expect(pageSource).toContain("onClick={openExportDialog}");
    expect(pageSource).toContain('id="conversation-export-modal-title"');
    expect(pageSource).toContain("导出前可调整正文、标题和段落格式");
    expect(pageSource).toContain(
      '<details className="export-word-settings" open>',
    );
    expect(pageSource).toContain("正文字体");
    expect(pageSource).toContain("正文字号");
    expect(pageSource).toContain("行间距");
    expect(pageSource).toContain("标题字体");
    expect(pageSource).toContain("标题起始等级");
    expect(pageSource).toContain("exportDocx.mutate(wordFormat)");
  });

  it("sends the selected Word settings to the conversation export API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(["docx"]), {
        status: 200,
        headers: {
          "Content-Type":
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await exportConversationDocx({
      title: "智策对话记录",
      messages: [{ role: "assistant", content: "研究总结" }],
      wordFormat: {
        bodyFont: "宋体",
        bodyFontSizePt: 14,
        lineSpacing: 2,
        headingFont: "楷体",
        headingStartLevel: 2,
      },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/exports/conversation.docx",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          title: "智策对话记录",
          messages: [{ role: "assistant", content: "研究总结" }],
          word_format: {
            body_font: "宋体",
            body_font_size_pt: 14,
            line_spacing: 2,
            heading_font: "楷体",
            heading_start_level: 2,
          },
        }),
      }),
    );
  });
});
