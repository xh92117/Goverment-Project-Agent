"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldCheckIcon } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import {
  authDestination,
  probeAuthState,
  type AuthSurface,
} from "@/features/auth/route-policy";
import { Button } from "@/shared/ui/button";

export const AUTH_STATE_QUERY_KEY = ["auth", "state"] as const;

export function AuthGate({
  surface,
  children,
}: Readonly<{ surface: AuthSurface; children: React.ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const authState = useQuery({
    queryKey: AUTH_STATE_QUERY_KEY,
    queryFn: probeAuthState,
    retry: false,
    staleTime: 0,
  });

  const destination = authState.data
    ? authDestination(
        surface,
        authState.data,
        `${pathname}${typeof window === "undefined" ? "" : window.location.search}`,
      )
    : null;

  useEffect(() => {
    if (destination) router.replace(destination);
  }, [destination, router]);

  if (authState.isError) {
    return (
      <div className="auth-status-screen">
        <div className="auth-status-card" role="alert">
          <ShieldCheckIcon aria-hidden="true" />
          <strong>暂时无法验证登录状态</strong>
          <span>{authState.error instanceof Error ? authState.error.message : "请检查服务连接后重试。"}</span>
          <Button type="button" variant="primary" onClick={() => void authState.refetch()}>
            重新验证
          </Button>
        </div>
      </div>
    );
  }

  if (authState.isPending || destination) {
    return (
      <div className="auth-status-screen" aria-live="polite">
        <div className="auth-status-card compact">
          <span className="workspace-loading-spinner" aria-hidden="true" />
          <span>正在验证访问权限…</span>
        </div>
      </div>
    );
  }

  return children;
}
