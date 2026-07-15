import { apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface User {
  id?: string;
  username?: string;
  email?: string | null;
  role?: string;
}

export interface SetupStatus {
  initialized?: boolean;
  setup_required?: boolean;
  local_auth_enabled?: boolean;
}

export function setupStatus() {
  return apiJson<SetupStatus>("/api/v1/auth/setup-status");
}

export function me() {
  return apiJson<User>("/api/v1/auth/me");
}

export async function loginLocal(username: string, password: string) {
  // Backend uses OAuth2PasswordRequestForm which expects
  // application/x-www-form-urlencoded, not JSON.
  const form = new URLSearchParams();
  form.set("username", username);
  form.set("password", password);
  const response = await apiFetch("/api/v1/auth/login/local", {
    method: "POST",
    body: form.toString(),
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => undefined);
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `登录失败：HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<{ user?: User; access_token?: string }>;
}

export function initializeAdmin(input: { email: string; password: string }) {
  return apiJson<User>("/api/v1/auth/initialize", {
    method: "POST",
    body: jsonBody(input),
  });
}

export function logout() {
  return apiJson<{ message: string }>("/api/v1/auth/logout", { method: "POST" });
}
