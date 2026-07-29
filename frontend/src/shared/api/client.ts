import { backendBaseUrl } from "./config";

const STATE_CHANGING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function csrfToken() {
  if (typeof document === "undefined") return null;
  const prefix = "csrf_token=";
  for (const pair of document.cookie.split("; ")) {
    if (pair.startsWith(prefix)) return decodeURIComponent(pair.slice(prefix.length));
  }
  return null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function responseMessage(body: unknown, status: number) {
  if (typeof body === "object" && body) {
    const payload = body as { detail?: unknown; message?: unknown };
    if (typeof payload.detail === "string" && payload.detail) return payload.detail;
    if (typeof payload.detail === "object" && payload.detail) {
      const nested = payload.detail as { message?: unknown };
      if (typeof nested.message === "string" && nested.message) return nested.message;
    }
    if (typeof payload.message === "string" && payload.message) return payload.message;
  }
  return `请求失败：HTTP ${status}`;
}

export async function apiErrorFromResponse(response: Response) {
  const detail = await response.json().catch(() => undefined);
  return new ApiError(responseMessage(detail, response.status), response.status, detail);
}

export function apiUrl(path: string) {
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${backendBaseUrl()}${clean}`;
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (STATE_CHANGING.has(method)) {
    const token = csrfToken();
    if (token && !headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", token);
  }

  return fetch(apiUrl(path), {
    ...init,
    headers,
    credentials: "include",
  });
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    throw await apiErrorFromResponse(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function jsonBody(value: unknown) {
  return JSON.stringify(value);
}
