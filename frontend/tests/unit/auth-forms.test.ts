import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { validatePasswordConfirmation } from "@/features/auth/form-validation";

describe("authentication forms", () => {
  it("validates minimum password length and matching confirmation", () => {
    expect(validatePasswordConfirmation("short", "short")).toBe("密码至少需要 8 位");
    expect(validatePasswordConfirmation("Secure2026", "Secure2027")).toBe("两次输入的密码不一致");
    expect(validatePasswordConfirmation("Secure2026", "Secure2026")).toBeNull();
  });

  it("wires login, registration and administrator setup through auth gates", () => {
    const login = readFileSync(new URL("../../src/app/(auth)/login/page.tsx", import.meta.url), "utf8");
    const register = readFileSync(new URL("../../src/app/(auth)/register/page.tsx", import.meta.url), "utf8");
    const setup = readFileSync(new URL("../../src/app/(auth)/setup/page.tsx", import.meta.url), "utf8");

    expect(login).toContain('<AuthGate surface="login">');
    expect(login).toContain('href="/register"');
    expect(login).toContain("safeWorkspaceDestination");
    expect(register).toContain('<AuthGate surface="register">');
    expect(register).toContain("registerLocal");
    expect(register).toContain("confirmPassword");
    expect(setup).toContain('<AuthGate surface="setup">');
    expect(setup).toContain("initializeAdmin");
    expect(setup).toContain("confirmPassword");
  });
});
