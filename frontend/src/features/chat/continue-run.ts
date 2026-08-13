import type { LocalMessage } from "@/features/chat/message-utils";

const CONTINUE_REQUEST_PATTERN = /^(继续|继续生成|继续回答|继续写|接着|接着写|往下写|请继续)[。.!！\s]*$/i;

const STOP_MARKERS = [
  "本次运行已停止",
  "工具调用次数超过安全上限",
  "未能生成完整最终回答",
  "本次运行未生成最终回答",
  "[FORCED STOP]",
];

export function shouldContinueStoppedRun(content: string, messages: LocalMessage[]) {
  if (!CONTINUE_REQUEST_PATTERN.test(content.trim())) return false;
  return messages
    .slice(-12)
    .some((message) => message.role === "assistant" && STOP_MARKERS.some((marker) => message.content.includes(marker)));
}

export function continuationRunContext(content: string, messages: LocalMessage[]) {
  return shouldContinueStoppedRun(content, messages) ? { continue_after_tool_stop: true } : undefined;
}
