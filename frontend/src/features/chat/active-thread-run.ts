import { useEffect, useState } from "react";

import { cancelRun, streamRun } from "@/features/chat/api";
import type { StreamAction } from "@/features/chat/api";
import type { LocalMessage } from "@/features/chat/message-utils";

export type ActiveThreadRunStatus = "running" | "success" | "error" | "cancelled";

export interface ActiveThreadRunSnapshot {
  threadId: string;
  runId: string | null;
  status: ActiveThreadRunStatus;
  messages: LocalMessage[];
  error?: string;
}

interface ActiveThreadRunSession extends ActiveThreadRunSnapshot {
  assistantId: string;
  controller: AbortController;
  cleanupTimer?: ReturnType<typeof setTimeout>;
}

interface StartThreadRunInput {
  threadId: string;
  content: string;
  assistantId: string;
  messages: LocalMessage[];
  context?: Record<string, unknown>;
  onComplete?: (status: ActiveThreadRunStatus) => void | Promise<void>;
}

type Listener = () => void;

const sessions = new Map<string, ActiveThreadRunSession>();
const listeners = new Map<string, Set<Listener>>();

export function mergeStreamAction(actions: StreamAction[] | undefined, next: StreamAction) {
  const current = actions ?? [];
  const index = current.findIndex((action) => action.id === next.id);
  if (index === -1) return [...current, next];
  return current.map((action, actionIndex) => (actionIndex === index ? { ...action, ...next } : action));
}

function cloneMessage(message: LocalMessage): LocalMessage {
  return {
    ...message,
    actions: message.actions ? message.actions.map((action) => ({ ...action })) : undefined,
  };
}

function snapshot(session: ActiveThreadRunSession): ActiveThreadRunSnapshot {
  return {
    threadId: session.threadId,
    runId: session.runId,
    status: session.status,
    messages: session.messages.map(cloneMessage),
    error: session.error,
  };
}

function notify(threadId: string) {
  listeners.get(threadId)?.forEach((listener) => listener());
}

function updateAssistantMessage(
  session: ActiveThreadRunSession,
  assistantId: string,
  update: (message: LocalMessage) => LocalMessage,
) {
  session.messages = session.messages.map((message) =>
    message.id === assistantId ? update(message) : message,
  );
}

function scheduleCleanup(threadId: string) {
  const session = sessions.get(threadId);
  if (!session || session.status === "running") return;
  if (session.cleanupTimer) clearTimeout(session.cleanupTimer);
  session.cleanupTimer = setTimeout(() => {
    const current = sessions.get(threadId);
    if (current && current.status !== "running") {
      sessions.delete(threadId);
      notify(threadId);
    }
  }, 5 * 60 * 1000);
}

export function getThreadRunSnapshot(threadId: string) {
  const session = threadId ? sessions.get(threadId) : undefined;
  return session ? snapshot(session) : null;
}

export function subscribeThreadRun(threadId: string, listener: Listener) {
  if (!threadId) return () => undefined;
  const threadListeners = listeners.get(threadId) ?? new Set<Listener>();
  threadListeners.add(listener);
  listeners.set(threadId, threadListeners);
  return () => {
    threadListeners.delete(listener);
    if (threadListeners.size === 0) listeners.delete(threadId);
  };
}

export function clearThreadRun(threadId: string) {
  const session = sessions.get(threadId);
  if (session?.cleanupTimer) clearTimeout(session.cleanupTimer);
  sessions.delete(threadId);
  notify(threadId);
}

export function startThreadRun({
  threadId,
  content,
  assistantId,
  messages,
  context,
  onComplete,
}: StartThreadRunInput) {
  const existing = sessions.get(threadId);
  if (existing?.status === "running") return snapshot(existing);
  if (existing?.cleanupTimer) clearTimeout(existing.cleanupTimer);

  const controller = new AbortController();
  const session: ActiveThreadRunSession = {
    threadId,
    runId: null,
    status: "running",
    assistantId,
    messages: messages.map(cloneMessage),
    controller,
  };
  sessions.set(threadId, session);
  notify(threadId);

  let pendingText = "";
  let textFlushHandle: ReturnType<typeof setTimeout> | number | null = null;
  let textFlushHandleKind: "animation-frame" | "timeout" | null = null;

  function clearTextFlushHandle() {
    if (textFlushHandle === null) return;
    if (textFlushHandleKind === "animation-frame" && typeof window !== "undefined") {
      window.cancelAnimationFrame(textFlushHandle as number);
    } else {
      clearTimeout(textFlushHandle as ReturnType<typeof setTimeout>);
    }
    textFlushHandle = null;
    textFlushHandleKind = null;
  }

  function flushPendingText() {
    textFlushHandle = null;
    textFlushHandleKind = null;
    if (!pendingText) return;
    const chunk = pendingText;
    pendingText = "";
    const current = sessions.get(threadId);
    if (!current || current !== session) return;
    updateAssistantMessage(current, assistantId, (message) => ({
      ...message,
      content: message.content + chunk,
    }));
    notify(threadId);
  }

  function scheduleTextFlush() {
    if (textFlushHandle !== null) return;
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      textFlushHandle = window.requestAnimationFrame(flushPendingText);
      textFlushHandleKind = "animation-frame";
      return;
    }
    if (typeof window === "undefined") {
      flushPendingText();
      return;
    }
    textFlushHandle = setTimeout(flushPendingText, 16);
    textFlushHandleKind = "timeout";
  }

  void streamRun({
    threadId,
    content,
    signal: controller.signal,
    context,
    onRunId: (nextRunId) => {
      const current = sessions.get(threadId);
      if (!current || current !== session) return;
      current.runId = nextRunId;
      notify(threadId);
    },
    onText: (chunk) => {
      const current = sessions.get(threadId);
      if (!current || current !== session) return;
      pendingText += chunk;
      scheduleTextFlush();
    },
    onAction: (action) => {
      const current = sessions.get(threadId);
      if (!current || current !== session) return;
      updateAssistantMessage(current, assistantId, (message) => ({
        ...message,
        actions: mergeStreamAction(message.actions, action),
      }));
      notify(threadId);
    },
  })
    .then(async () => {
      const current = sessions.get(threadId);
      if (!current || current !== session) return;
      clearTextFlushHandle();
      flushPendingText();
      updateAssistantMessage(current, assistantId, (message) =>
        message.content.trim()
          ? message
          : {
              ...message,
              content: "本次运行未生成最终回答。可以发送“继续”，或点击重新生成、缩小问题范围后重试。",
            },
      );
      current.status = "success";
      notify(threadId);
      scheduleCleanup(threadId);
      await onComplete?.("success");
    })
    .catch(async (error: unknown) => {
      const current = sessions.get(threadId);
      if (!current || current !== session) return;
      clearTextFlushHandle();
      flushPendingText();
      const isAbort = error instanceof Error && error.name === "AbortError";
      current.status = isAbort ? "cancelled" : "error";
      current.error = isAbort ? undefined : error instanceof Error ? error.message : String(error);
      if (current.status === "error") {
        updateAssistantMessage(current, assistantId, (message) => ({
          ...message,
          content: message.content || `运行失败：${current.error ?? "未知错误"}`,
        }));
      }
      notify(threadId);
      scheduleCleanup(threadId);
      await onComplete?.(current.status);
    });

  return snapshot(session);
}

export async function stopThreadRun(threadId: string) {
  const session = sessions.get(threadId);
  if (session?.status !== "running") return;
  session.controller.abort();
  session.status = "cancelled";
  notify(threadId);
  if (session.runId) await cancelRun(threadId, session.runId).catch(() => undefined);
  scheduleCleanup(threadId);
}

export function useActiveThreadRun(threadId: string) {
  const [current, setCurrent] = useState<ActiveThreadRunSnapshot | null>(() => getThreadRunSnapshot(threadId));

  useEffect(() => {
    setCurrent(getThreadRunSnapshot(threadId));
    return subscribeThreadRun(threadId, () => {
      setCurrent(getThreadRunSnapshot(threadId));
    });
  }, [threadId]);

  return current;
}
