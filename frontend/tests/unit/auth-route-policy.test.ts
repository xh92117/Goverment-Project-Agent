import { describe, expect, it } from "vitest";

import {
  authDestination,
  safeWorkspaceDestination,
  type AuthState,
} from "@/features/auth/route-policy";

describe("auth route policy", () => {
  it("keeps the existing workspace flow when local auth is disabled", () => {
    expect(authDestination("workspace", { kind: "disabled" }, "/workspace/projects")).toBeNull();
  });

  it("routes first boot to administrator initialization", () => {
    const state: AuthState = { kind: "setup-required" };

    expect(authDestination("workspace", state, "/workspace/projects")).toBe("/setup");
    expect(authDestination("login", state)).toBe("/setup");
    expect(authDestination("register", state)).toBe("/setup");
    expect(authDestination("setup", state)).toBeNull();
  });

  it("protects workspace routes and preserves a safe return path", () => {
    const state: AuthState = { kind: "anonymous" };

    expect(authDestination("workspace", state, "/workspace/projects/abc?tab=files")).toBe(
      "/login?next=%2Fworkspace%2Fprojects%2Fabc%3Ftab%3Dfiles",
    );
    expect(authDestination("login", state)).toBeNull();
    expect(authDestination("register", state)).toBeNull();
    expect(authDestination("setup", state)).toBe("/login");
  });

  it("keeps authenticated users out of public authentication pages", () => {
    const state: AuthState = {
      kind: "authenticated",
      user: { id: "user-1", email: "owner@example.com", system_role: "admin" },
    };

    expect(authDestination("workspace", state, "/workspace/projects")).toBeNull();
    expect(authDestination("login", state)).toBe("/workspace/projects");
    expect(authDestination("register", state)).toBe("/workspace/projects");
    expect(authDestination("setup", state)).toBe("/workspace/projects");
  });

  it("accepts only local workspace destinations after login", () => {
    expect(safeWorkspaceDestination("/workspace/knowledge?view=shared")).toBe(
      "/workspace/knowledge?view=shared",
    );
    expect(safeWorkspaceDestination("//attacker.example/redirect")).toBe("/workspace/projects");
    expect(safeWorkspaceDestination("https://attacker.example/redirect")).toBe(
      "/workspace/projects",
    );
    expect(safeWorkspaceDestination("/setup")).toBe("/workspace/projects");
    expect(safeWorkspaceDestination(null)).toBe("/workspace/projects");
  });
});
