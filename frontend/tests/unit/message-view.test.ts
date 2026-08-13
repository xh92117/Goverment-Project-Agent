import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { buildTurns } from "@/features/chat/message-turns";

describe("message turns", () => {
  it("collapses regenerated answers into the original user turn", () => {
    const turns = buildTurns([
      { id: "user-1", role: "user", content: "Please explain tunnel lining detection." },
      { id: "assistant-1", role: "assistant", content: "Old answer." },
      { id: "user-2", role: "user", content: "Please explain tunnel lining detection." },
      { id: "assistant-2", role: "assistant", content: "New answer." },
    ]);

    expect(turns).toHaveLength(1);
    expect(turns[0]?.user?.id).toBe("user-1");
    expect(turns[0]?.assistantIds).toEqual(["assistant-2"]);
    expect(turns[0]?.assistant?.content).toBe("New answer.");
  });

  it("expands stream actions while running and moves them below completed answers", () => {
    const source = readFileSync(
      new URL("../../src/features/chat/message-view.tsx", import.meta.url),
      "utf8",
    );
    const runningActionsIndex = source.indexOf("{isStreaming ? actionPanel : null}");
    const contentIndex = source.indexOf('className="msg-content"', runningActionsIndex);
    const completedActionsIndex = source.indexOf("{!isStreaming ? actionPanel : null}", contentIndex);

    expect(source).toContain("const shouldForceOpen = isStreaming === true || hasRunningAction;");
    expect(source).toContain("open={open}");
    expect(source).toContain("setOpen(shouldForceOpen);");
    expect(runningActionsIndex).toBeGreaterThan(-1);
    expect(contentIndex).toBeGreaterThan(runningActionsIndex);
    expect(completedActionsIndex).toBeGreaterThan(contentIndex);
  });

  it("routes assistant markdown through the shared renderer with streaming state", () => {
    const source = readFileSync(
      new URL("../../src/features/chat/message-view.tsx", import.meta.url),
      "utf8",
    );

    expect(source).toContain('import { MarkdownRenderer } from "@/features/chat/markdown-renderer"');
    expect(source).toContain("<MarkdownRenderer content={assistant.content} isStreaming={isStreaming} onCopied={onCopied} />");
    expect(source).toContain('className={`msg ai${isStreaming ? " streaming" : ""}`}');
  });

  it("shows the user label only in the avatar", () => {
    const source = readFileSync(
      new URL("../../src/features/chat/message-view.tsx", import.meta.url),
      "utf8",
    );

    expect(source).toContain('<div className="msg-avatar">我</div>');
    expect(source).not.toContain('<div className="msg-name">我</div>');
  });
});
