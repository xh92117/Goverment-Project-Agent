import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("workspace collapse layout", () => {
  it("lets the main conversation area resize when sidebars collapse", () => {
    const source = readFileSync(
      new URL("../../src/styles/codex-workbench.css", import.meta.url),
      "utf8",
    );

    expect(source).toContain(".app.collapse-left {\n  grid-template-columns: minmax(0, 1fr);");
    expect(source).toContain(".app.collapse-left .workspace-slot {\n  grid-column: 1;\n}");
    expect(source).toContain(".app.collapse-left .main-head {\n  padding-left: 52px;\n}");
    expect(source).toContain(".project-page-grid.right-collapsed {\n  grid-template-columns: minmax(0, 1fr) 44px;");
    expect(source).toContain(".app.collapse-left .codex-main,\n.project-page-grid.right-collapsed .codex-main");
    expect(source).toContain(".app.collapse-left .project-page-grid.right-collapsed .codex-main");
    expect(source).toContain("width: min(100%, var(--chat-content-max, 880px));");
  });
});
