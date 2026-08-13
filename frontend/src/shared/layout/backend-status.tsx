"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertCircleIcon, CheckCircle2Icon, Loader2Icon } from "lucide-react";

import { checkBackend } from "@/shared/api/health";

export function BackendStatus() {
  const status = useQuery({
    queryKey: ["backend-status"],
    queryFn: checkBackend,
    refetchInterval: 15_000,
    retry: 0,
  });

  if (status.isLoading) {
    return (
      <span className="status-pill muted">
        <Loader2Icon size={14} className="spin" />
        后端检测中
      </span>
    );
  }

  if (status.isError) {
    return (
      <span className="status-pill danger" title="请确认后端网关已启动，并通过同源 /api 代理访问">
        <AlertCircleIcon size={14} />
        后端未连接
      </span>
    );
  }

  return (
    <span className="status-pill success">
      <CheckCircle2Icon size={14} />
      后端已连接
    </span>
  );
}
