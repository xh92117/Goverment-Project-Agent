import type { AuthState } from "@/features/auth/route-policy";

import type { KnowledgeScope } from "./api";

export function canManagePublicKnowledge(state: AuthState | undefined) {
  if (state?.kind === "disabled") return true;
  return state?.kind === "authenticated" && state.user.system_role === "admin";
}

export function canReadPublicKnowledge(state: AuthState | undefined) {
  if (state?.kind === "disabled") return true;
  return state?.kind === "authenticated";
}

export function defaultKnowledgeScope(
  state: AuthState | undefined,
): KnowledgeScope {
  return canReadPublicKnowledge(state) ? "public" : "private";
}
