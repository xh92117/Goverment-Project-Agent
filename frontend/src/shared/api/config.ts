import { env } from "@/env";

function originFallback() {
  if (typeof window !== "undefined") return window.location.origin;
  return "http://127.0.0.1:9527";
}

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

export function backendBaseUrl() {
  const configured = env.NEXT_PUBLIC_BACKEND_BASE_URL?.trim();
  if (!configured) return "";
  return trimTrailingSlash(new URL(configured, originFallback()).toString());
}

export function langgraphBaseUrl() {
  const configured = env.NEXT_PUBLIC_LANGGRAPH_BASE_URL?.trim();
  if (configured) return trimTrailingSlash(new URL(configured, originFallback()).toString());
  return `${originFallback()}/api/langgraph`;
}
