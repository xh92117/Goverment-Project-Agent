"use client";

import { useCallback, useEffect, useState } from "react";

import { normalizeExecutionMode, type ExecutionMode } from "@/features/chat/api";

const EXECUTION_MODE_STORAGE_KEY = "chat-execution-mode";

export function useExecutionMode() {
  const [executionMode, setExecutionModeState] = useState<ExecutionMode>("standard");

  useEffect(() => {
    try {
      setExecutionModeState(normalizeExecutionMode(window.localStorage.getItem(EXECUTION_MODE_STORAGE_KEY)));
    } catch {
      setExecutionModeState("standard");
    }
  }, []);

  const setExecutionMode = useCallback((mode: ExecutionMode) => {
    setExecutionModeState(mode);
    try {
      window.localStorage.setItem(EXECUTION_MODE_STORAGE_KEY, mode);
    } catch {
      // Storage is optional; keep the in-memory mode for this page session.
    }
  }, []);

  return [executionMode, setExecutionMode] as const;
}
