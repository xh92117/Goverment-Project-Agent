import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("runtime path settings", () => {
  const pageSource = readFileSync(
    new URL("../../src/features/settings/settings-page.tsx", import.meta.url),
    "utf8",
  );
  const apiSource = readFileSync(
    new URL("../../src/features/settings/api.ts", import.meta.url),
    "utf8",
  );

  it("loads and persists runtime paths through the dedicated settings API", () => {
    expect(apiSource).toContain("loadRuntimePathConfig");
    expect(apiSource).toContain("updateRuntimePathConfig");
    expect(apiSource).toContain('"/api/settings/runtime-paths"');
  });

  it("exposes storage paths and explains env persistence and restart", () => {
    expect(pageSource).toContain('id: "storage"');
    expect(pageSource).toContain("存储目录");
    expect(pageSource).toContain("GP_AGENT_HOME");
    expect(pageSource).toContain(".env");
    expect(pageSource).toContain("重启");
  });
});
