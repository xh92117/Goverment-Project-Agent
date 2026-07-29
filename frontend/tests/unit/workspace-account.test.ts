import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("workspace account entry", () => {
  it("shows the authenticated account and clears user-scoped cache on logout", () => {
    const account = readFileSync(
      new URL("../../src/features/auth/workspace-account.tsx", import.meta.url),
      "utf8",
    );
    const shell = readFileSync(
      new URL("../../src/shared/layout/workspace-shell.tsx", import.meta.url),
      "utf8",
    );

    expect(account).toContain("system_role");
    expect(account).toContain("await logout()");
    expect(account).toContain("queryClient.clear()");
    expect(account).toContain('router.replace("/login")');
    expect(shell).toContain("<WorkspaceAccount />");
  });
});
