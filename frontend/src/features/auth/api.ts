import { apiErrorFromResponse, apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface User {
  id: string;
  email: string | null;
  system_role: string;
  needs_setup?: boolean;
}

export interface SetupStatus {
  needs_setup: boolean;
}

export interface LoginResponse {
  expires_in: number;
  needs_setup: boolean;
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
    throw await apiErrorFromResponse(response);
  }
  return response.json() as Promise<LoginResponse>;
}

export function registerLocal(input: { email: string; password: string }) {
  return apiJson<User>("/api/v1/auth/register", {
    method: "POST",
    body: jsonBody(input),
  });
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
