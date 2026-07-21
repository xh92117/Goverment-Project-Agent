import { me, setupStatus } from "@/features/auth/api";
import type { User } from "@/features/auth/api";
import { ApiError } from "@/shared/api/client";

export const WORKSPACE_HOME = "/workspace/projects";

export type AuthSurface = "workspace" | "login" | "register" | "setup";

export type AuthState =
  | { kind: "disabled" }
  | { kind: "setup-required" }
  | { kind: "anonymous" }
  | { kind: "authenticated"; user: User };

export function safeWorkspaceDestination(value: string | null | undefined) {
  if (!value || !value.startsWith("/workspace") || value.startsWith("//")) {
    return WORKSPACE_HOME;
  }
  return value;
}

export function authDestination(
  surface: AuthSurface,
  state: AuthState,
  currentPath = WORKSPACE_HOME,
): string | null {
  if (state.kind === "disabled") {
    return surface === "workspace" ? null : WORKSPACE_HOME;
  }

  if (state.kind === "setup-required") {
    return surface === "setup" ? null : "/setup";
  }

  if (state.kind === "authenticated") {
    return surface === "workspace" ? null : WORKSPACE_HOME;
  }

  if (surface === "workspace") {
    const next = safeWorkspaceDestination(currentPath);
    return `/login?next=${encodeURIComponent(next)}`;
  }
  if (surface === "setup") return "/login";
  return null;
}

export async function probeAuthState(): Promise<AuthState> {
  let status;
  try {
    status = await setupStatus();
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { kind: "disabled" };
    throw error;
  }

  if (status.needs_setup) return { kind: "setup-required" };

  try {
    return { kind: "authenticated", user: await me() };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return { kind: "anonymous" };
    throw error;
  }
}
