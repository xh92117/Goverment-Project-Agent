import { apiJson } from "./client";

export async function checkBackend() {
  await apiJson<{ models?: unknown[] }>("/api/models");
  return { ok: true };
}
