"use client";

import { GaugeIcon, SearchIcon } from "lucide-react";

import type { ExecutionMode } from "@/features/chat/api";

export function ExecutionModeToggle({
  value,
  disabled,
  onChange,
}: {
  value: ExecutionMode;
  disabled?: boolean;
  onChange: (mode: ExecutionMode) => void;
}) {
  const isDeep = value === "deep";
  const nextMode: ExecutionMode = isDeep ? "standard" : "deep";

  return (
    <button
      type="button"
      className={`execution-mode-toggle${isDeep ? " deep" : ""}`}
      disabled={disabled}
      title={isDeep ? "深度模式：增加工具调用预算，适合资料检索、申报书写作和多步骤任务" : "标准模式：更快响应，适合普通问答和小改动"}
      aria-label="执行强度"
      aria-pressed={isDeep}
      onClick={() => onChange(nextMode)}
    >
      {isDeep ? <SearchIcon size={14} /> : <GaugeIcon size={14} />}
      {isDeep ? "深度模式" : "标准模式"}
    </button>
  );
}
