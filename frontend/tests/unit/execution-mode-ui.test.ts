import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("execution mode UI wiring", () => {
  it("passes execution_mode from chat and project composers into run context", () => {
    const chatPage = readFileSync(
      new URL("../../src/features/chat/chat-page.tsx", import.meta.url),
      "utf8",
    );
    const projectPage = readFileSync(
      new URL("../../src/features/projects/project-workspace-page.tsx", import.meta.url),
      "utf8",
    );
    const toggle = readFileSync(
      new URL("../../src/features/chat/execution-mode-toggle.tsx", import.meta.url),
      "utf8",
    );

    expect(chatPage).toContain("const [executionMode, setExecutionMode] = useExecutionMode();");
    expect(chatPage).toContain("execution_mode: executionMode");
    expect(chatPage).toContain("<ExecutionModeToggle value={executionMode} disabled={isRunning} onChange={setExecutionMode} />");

    expect(projectPage).toContain("const [executionMode, setExecutionMode] = useExecutionMode();");
    expect(projectPage).toContain("execution_mode: executionMode");
    expect(projectPage).toMatch(
      /<ExecutionModeToggle\s+value=\{executionMode\}\s+disabled=\{isRunning\}\s+onChange=\{setExecutionMode\}\s*\/>/,
    );
    expect(projectPage.indexOf("onClick={openDirectoryDialog}")).toBeLessThan(projectPage.indexOf('<div className="cb-right">'));
    expect(projectPage).toContain("项目工作区");

    expect(toggle).toContain('aria-label="执行强度"');
    expect(toggle).toContain('const nextMode: ExecutionMode = isDeep ? "standard" : "deep";');
    expect(toggle).toContain("标准模式");
    expect(toggle).toContain("深度模式");
    expect(toggle).toContain("onClick={() => onChange(nextMode)}");
  });
});
