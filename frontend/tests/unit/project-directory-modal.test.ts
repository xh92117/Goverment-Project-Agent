import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("project directory modal", () => {
  it("does not show redundant default path or creation metadata", () => {
    const source = readFileSync(
      new URL("../../src/features/projects/project-workspace-page.tsx", import.meta.url),
      "utf8",
    );
    const directoryModalStart = source.indexOf('aria-labelledby="directory-modal-title"');
    const directoryModalEnd = source.indexOf("{fileDialogOpen && selectedFile ?", directoryModalStart);
    const modalSource = source.slice(directoryModalStart, directoryModalEnd);

    expect(modalSource).toContain('<h2 id="directory-modal-title">打开项目目录</h2>');
    expect(modalSource).not.toContain("<span>项目目录</span>");
    expect(modalSource).not.toContain("已创建");
    expect(modalSource).not.toContain("<span>默认</span>");
    expect(modalSource).not.toContain("default_root_path");
  });
});
