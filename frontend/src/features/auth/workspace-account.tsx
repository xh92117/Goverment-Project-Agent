"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LogOutIcon, Settings2Icon, ShieldCheckIcon, UserRoundIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { logout } from "@/features/auth/api";
import { AUTH_STATE_QUERY_KEY } from "@/features/auth/auth-gate";
import { authErrorMessage } from "@/features/auth/form-validation";
import { probeAuthState } from "@/features/auth/route-policy";

export function WorkspaceAccount() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const authState = useQuery({
    queryKey: AUTH_STATE_QUERY_KEY,
    queryFn: probeAuthState,
    retry: false,
    staleTime: 60_000,
  });

  if (authState.data?.kind !== "authenticated") return null;

  const user = authState.data.user;
  const isAdmin = user.system_role === "admin";
  const email = user.email ?? "未绑定邮箱";
  const avatar = email.slice(0, 1).toUpperCase() || "用";

  async function signOut() {
    setLoggingOut(true);
    setError(null);
    try {
      await logout();
      queryClient.clear();
      router.replace("/login");
    } catch (caught) {
      setError(authErrorMessage(caught));
      setLoggingOut(false);
    }
  }

  return (
    <details className="workspace-account">
      <summary className="workspace-account-trigger">
        <span className="workspace-account-avatar" aria-hidden="true">{avatar}</span>
        <span className="workspace-account-identity">
          <strong>{email}</strong>
          <small>{isAdmin ? "系统管理员" : "普通用户"}</small>
        </span>
        {isAdmin ? <ShieldCheckIcon className="workspace-account-role" aria-label="管理员账号" /> : <UserRoundIcon className="workspace-account-role" aria-label="普通用户账号" />}
      </summary>

      <div className="workspace-account-menu">
        <div className="workspace-account-menu-head">
          <span className="workspace-account-avatar large" aria-hidden="true">{avatar}</span>
          <span>
            <strong>{email}</strong>
            <small>{isAdmin ? "管理员账号" : "个人账号"}</small>
          </span>
        </div>
        {isAdmin ? (
          <Link href="/workspace/settings">
            <Settings2Icon aria-hidden="true" />
            系统设置
          </Link>
        ) : null}
        <button type="button" disabled={loggingOut} onClick={() => void signOut()}>
          <LogOutIcon aria-hidden="true" />
          {loggingOut ? "正在退出…" : "退出登录"}
        </button>
        {error ? <div className="workspace-account-error" role="alert">{error}</div> : null}
      </div>
    </details>
  );
}
