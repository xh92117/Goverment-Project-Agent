import { apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface ThreadRecord {
  thread_id: string;
  status: string;
  created_at?: string;
  updated_at?: string;
  metadata?: Record<string, unknown>;
  values?: Record<string, unknown>;
}

export interface ChatMessage {
  id?: string;
  type?: string;
  role?: string;
  content?: unknown;
  additional_kwargs?: Record<string, unknown>;
  event_type?: string;
  category?: string;
  seq?: number;
  created_at?: string;
}

export interface RunRecord {
  run_id: string;
  thread_id: string;
  status: string;
  total_tokens?: number;
  message_count?: number;
}

export type StreamActionStatus = "running" | "completed" | "error";

export interface StreamAction {
  id: string;
  kind: "tool" | "status";
  status: StreamActionStatus;
  title: string;
  detail?: string;
  toolName?: string;
}

export interface UploadLimits {
  max_files?: number;
  max_file_size_mb?: number;
  allowed_extensions?: string[];
}

export interface UploadList {
  files?: Array<{ filename: string; size?: number; content_type?: string }>;
}

export const GOVERNMENT_PROJECT_ASSISTANT_ID = "government-project-declaration";

export type ExecutionMode = "standard" | "deep";

export function normalizeExecutionMode(value: unknown): ExecutionMode {
  return value === "deep" ? "deep" : "standard";
}

export function createThread(threadId: string, metadata: Record<string, unknown>) {
  return apiJson<ThreadRecord>("/api/threads", {
    method: "POST",
    body: jsonBody({
      thread_id: threadId,
      assistant_id: GOVERNMENT_PROJECT_ASSISTANT_ID,
      metadata,
    }),
  });
}

export function searchThreads(limit = 80, metadata: Record<string, unknown> = {}) {
  return apiJson<ThreadRecord[]>("/api/threads/search", {
    method: "POST",
    body: jsonBody({ limit, offset: 0, metadata }),
  });
}

export function patchThread(threadId: string, metadata: Record<string, unknown>) {
  return apiJson<ThreadRecord>(`/api/threads/${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    body: jsonBody({ metadata }),
  });
}

export function deleteThread(threadId: string) {
  return apiJson<{ success: boolean; message: string }>(
    `/api/threads/${encodeURIComponent(threadId)}`,
    { method: "DELETE" },
  );
}

export function getThreadMessages(threadId: string) {
  return apiJson<{ messages?: ChatMessage[] } | ChatMessage[]>(
    `/api/threads/${encodeURIComponent(threadId)}/messages`,
  );
}

export function listRuns(threadId: string) {
  return apiJson<RunRecord[]>(`/api/threads/${encodeURIComponent(threadId)}/runs`);
}

export function cancelRun(threadId: string, runId: string) {
  return apiJson<RunRecord>(
    `/api/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/cancel`,
    { method: "POST" },
  );
}

export function tokenUsage(threadId: string) {
  return apiJson<{
    total_tokens: number;
    total_input_tokens: number;
    total_output_tokens: number;
    total_runs: number;
  }>(`/api/threads/${encodeURIComponent(threadId)}/token-usage`);
}

export function uploadFile(threadId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiJson<unknown>(`/api/threads/${encodeURIComponent(threadId)}/uploads`, {
    method: "POST",
    body: form,
  });
}

export function uploadLimits(threadId: string) {
  return apiJson<UploadLimits>(`/api/threads/${encodeURIComponent(threadId)}/uploads/limits`);
}

export function uploadList(threadId: string) {
  return apiJson<UploadList>(`/api/threads/${encodeURIComponent(threadId)}/uploads/list`);
}

export async function exportConversationDocx(input: {
  title: string;
  messages: Array<{ role: "user" | "assistant"; content: string }>;
}) {
  const response = await apiFetch("/api/exports/conversation.docx", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: jsonBody(input),
  });
  if (!response.ok) {
    throw new Error(`导出失败：HTTP ${response.status}`);
  }
  return response.blob();
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function compactText(value: unknown, maxLength = 120): string | undefined {
  let text = "";
  if (typeof value === "string") {
    text = value;
  } else if (Array.isArray(value)) {
    text = value
      .map((item) => {
        if (typeof item === "string") return item;
        const record = asRecord(item);
        return asString(record?.text) ?? asString(record?.content) ?? "";
      })
      .join("");
  } else if (value !== undefined && value !== null) {
    try {
      text = JSON.stringify(value);
    } catch {
      text = value instanceof Error ? value.message : Object.prototype.toString.call(value);
    }
  }
  const normalized = text.replace(/\s+/g, " ").trim();
  if (!normalized) return undefined;
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1)}...` : normalized;
}

export function extractMessageContent(payload: unknown): string | null {
  if (!Array.isArray(payload) || payload.length === 0) return null;
  const message = payload[0];
  if (!message || typeof message !== "object") return null;
  const record = message as Record<string, unknown>;
  const nested =
    asRecord(record.kwargs) ??
    asRecord(record.data) ??
    null;

  const rawType =
    asString(record.type) ??
    asString(record.role) ??
    asString(record.name) ??
    (Array.isArray(record.id) ? record.id.join(".") : asString(record.id)) ??
    asString(nested?.type) ??
    asString(nested?.role);
  if (!rawType) return null;
  const type = rawType.toLowerCase();
  if (type.includes("human") || type.includes("tool")) return null;

  const content = "content" in record ? record.content : nested?.content;
  if (typeof content === "string") {
    if (!content.trim()) return null;
    return isRawKnowledgePayload(content) ? null : content;
  }
  if (Array.isArray(content)) {
    const text = content
      .map((block): string => {
        if (typeof block === "string") return block;
        const recordBlock = asRecord(block);
        return asString(recordBlock?.text) ?? asString(recordBlock?.content) ?? "";
      })
      .join("");
    if (!text.trim()) return null;
    return isRawKnowledgePayload(text) ? null : text;
  }
  return null;
}

const TOOL_LABELS: Record<string, string> = {
  web_search: "检索网页",
  web_fetch: "读取网页",
  web_extract: "提取网页字段",
  knowledge_search: "检索知识库",
  knowledge_search_index: "检索知识库索引",
  knowledge_read_file: "读取知识库文件",
  glob: "查找文件",
  ls: "列出文件",
  read_file: "读取文件",
  task: "调用子任务",
  ask_clarification: "请求澄清",
  present_files: "整理文件",
};

function toolLabel(toolName?: string) {
  if (!toolName) return "工具调用";
  return TOOL_LABELS[toolName] ?? toolName.replace(/_/g, " ");
}

function toolTitle(toolName: string | undefined, status: StreamActionStatus) {
  const label = toolLabel(toolName);
  if (status === "running") return `正在${label}`;
  if (status === "error") return `${label}失败`;
  return `${label}完成`;
}

function toolCallDetail(toolName: string | undefined, args: unknown) {
  const record = asRecord(args);
  const primary =
    asString(record?.query) ??
    asString(record?.url) ??
    asString(record?.task) ??
    asString(record?.prompt) ??
    asString(record?.description) ??
    compactText(args);
  if (!primary) return undefined;
  if (toolName === "web_fetch") return compactText(primary, 150);
  if (toolName === "web_extract") {
    const fields = asString(record?.fields);
    return compactText(fields ? `字段：${fields}` : primary, 150);
  }
  if (toolName === "web_search") {
    const engine = asString(record?.engine);
    return compactText(engine ? `关键词：${primary} · 引擎：${engine}` : `关键词：${primary}`, 150);
  }
  if (toolName === "knowledge_search" || toolName === "knowledge_search_index") return compactText(`关键词：${primary}`, 150);
  return compactText(primary, 150);
}

function toolResultDetail(toolName: string | undefined, content: unknown, status: StreamActionStatus) {
  if (status === "error") return compactText(content, 150) ?? "工具执行返回错误";
  if (toolName === "web_search") return "已返回网页检索结果";
  if (toolName === "web_fetch") return "已读取网页内容";
  if (toolName === "web_extract") return "已提取网页字段";
  if (toolName === "knowledge_search") return "已返回知识库检索结果";
  if (toolName === "knowledge_search_index") return "已返回知识库索引结果";
  if (toolName === "knowledge_read_file") return "已读取知识库文件";
  if (toolName === "task") return "子任务已返回结果";
  return "已返回工具结果";
}

function getNestedRecord(record: Record<string, unknown>) {
  return asRecord(record.kwargs) ?? asRecord(record.data) ?? null;
}

function extractToolCallsFromRecord(record: Record<string, unknown>): StreamAction[] {
  const nested = getNestedRecord(record);
  const actions: StreamAction[] = [];
  const candidates = [record, nested].filter(Boolean) as Record<string, unknown>[];

  candidates.forEach((candidate) => {
    const toolCalls = candidate.tool_calls ?? candidate.tool_call_chunks;
    if (!Array.isArray(toolCalls)) return;
    toolCalls.forEach((rawCall, index) => {
      const call = asRecord(rawCall);
      if (!call) return;
      const fn = asRecord(call.function);
      const name =
        asString(call.name) ??
        asString(call.tool_name) ??
        asString(fn?.name);
      const callId =
        asString(call.id) ??
        asString(call.tool_call_id) ??
        asString(call.index) ??
        (name ? `${name}-${index}` : null);
      if (!callId || !name) return;
      const args = call.args ?? call.arguments ?? fn?.arguments ?? call.input;
      actions.push({
        id: `tool:${callId}`,
        kind: "tool",
        status: "running",
        toolName: name,
        title: toolTitle(name, "running"),
        detail: toolCallDetail(name, args),
      });
    });
  });
  return actions;
}

function extractToolResultFromRecord(record: Record<string, unknown>): StreamAction | null {
  const nested = getNestedRecord(record);
  const rawType =
    asString(record.type) ??
    asString(record.role) ??
    asString(record.name) ??
    asString(nested?.type) ??
    asString(nested?.role);
  const type = rawType?.toLowerCase() ?? "";
  const toolCallId = asString(record.tool_call_id) ?? asString(nested?.tool_call_id);
  if (!toolCallId || (!type.includes("tool") && !("tool_call_id" in record))) return null;
  const toolName = asString(record.name) ?? asString(nested?.name) ?? undefined;
  const content = "content" in record ? record.content : nested?.content;
  const contentText = compactText(content, 180);
  const isError =
    Boolean(asRecord(record.additional_kwargs)?.error) ||
    Boolean(contentText?.toLowerCase().startsWith("error:")) ||
    Boolean(contentText?.includes("ToolException"));
  const status: StreamActionStatus = isError ? "error" : "completed";
  return {
    id: `tool:${toolCallId}`,
    kind: "tool",
    status,
    toolName,
    title: toolTitle(toolName, status),
    detail: toolResultDetail(toolName, content, status),
  };
}

function extractStatusFromRecord(record: Record<string, unknown>, eventType?: string): StreamAction | null {
  const kind =
    asString(record.type) ??
    asString(record.event) ??
    asString(record.status) ??
    asString(record.name);
  const message =
    asString(record.message) ??
    asString(record.title) ??
    asString(record.detail) ??
    asString(record.status);
  const isStatusEvent = eventType === "custom" || eventType === "error";
  if (!message || (!isStatusEvent && !kind)) return null;
  const status: StreamActionStatus = eventType === "error" ? "error" : "running";
  const detail =
    status === "error"
      ? compactText(message, 180)
      : asString(record.detail) && asString(record.detail) !== message
        ? asString(record.detail) ?? undefined
        : undefined;
  return {
    id: `status:${kind ?? eventType ?? "event"}:${message.slice(0, 48)}`,
    kind: "status",
    status,
    title: status === "error" ? "运行失败" : message,
    detail,
  };
}

function extractStreamError(payload: unknown): string | null {
  const record = asRecord(payload);
  if (!record) return null;
  return asString(record.message) ?? asString(record.error) ?? asString(record.detail);
}

export function extractStreamActions(payload: unknown, eventType?: string): StreamAction[] {
  const actions: StreamAction[] = [];
  const seen = new Set<string>();

  function add(action: StreamAction | null) {
    if (!action) return;
    const key = `${action.id}:${action.status}:${action.title}:${action.detail ?? ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    actions.push(action);
  }

  function walk(value: unknown, depth = 0) {
    if (depth > 5) return;
    if (Array.isArray(value)) {
      value.forEach((item) => walk(item, depth + 1));
      return;
    }
    const record = asRecord(value);
    if (!record) return;

    extractToolCallsFromRecord(record).forEach(add);
    add(extractToolResultFromRecord(record));
    if (eventType === "custom" || eventType === "error") add(extractStatusFromRecord(record, eventType));

    Object.values(record).forEach((child) => {
      if (child && typeof child === "object") walk(child, depth + 1);
    });
  }

  walk(payload);
  return actions;
}

export function isRawKnowledgePayload(content: string) {
  const trimmed = content.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return false;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    const root = Array.isArray(parsed) ? parsed[0] : parsed;
    if (!root || typeof root !== "object") return false;
    const record = root as Record<string, unknown>;
    const results = record.results;
    if (!Array.isArray(results)) return false;
    return results.some((item) => {
      const entry = asRecord(item);
      if (!entry) return false;
      const payload = asRecord(entry.entry) ?? entry;
      return (
        "index_id" in payload ||
        "file_path" in payload ||
        "recommended_sections" in payload ||
        "summary" in payload
      );
    });
  } catch {
    return false;
  }
}

export async function streamRun({
  threadId,
  content,
  context,
  signal,
  onText,
  onRunId,
  onAction,
}: {
  threadId: string;
  content: string;
  context?: Record<string, unknown>;
  signal?: AbortSignal;
  onText: (chunk: string) => void;
  onRunId?: (runId: string) => void;
  onAction?: (action: StreamAction) => void;
}) {
  const response = await apiFetch(`/api/threads/${encodeURIComponent(threadId)}/runs/stream`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: jsonBody({
      assistant_id: GOVERNMENT_PROJECT_ASSISTANT_ID,
      input: { messages: [{ type: "human", content }] },
      context,
      stream_mode: ["messages", "updates", "custom"],
      if_not_exists: "create",
      on_disconnect: "continue",
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：HTTP ${response.status}`);
  }

  const location = response.headers.get("Content-Location");
  const runId = location?.split("/").filter(Boolean).at(-1);
  if (runId) onRunId?.(runId);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const actionSignatures = new Map<string, string>();
  const latestActions = new Map<string, StreamAction>();
  let runError: string | null = null;
  let streamedText = "";

  function emitAction(action: StreamAction) {
    const signature = `${action.status}:${action.title}:${action.detail ?? ""}:${action.toolName ?? ""}`;
    if (actionSignatures.get(action.id) === signature) return;
    actionSignatures.set(action.id, signature);
    latestActions.set(action.id, action);
    onAction?.(action);
  }

  function emitText(text: string) {
    if (!text) return;
    if (!streamedText) {
      streamedText = text;
      onText(text);
      return;
    }
    if (text === streamedText) return;
    if (text.startsWith(streamedText)) {
      const delta = text.slice(streamedText.length);
      streamedText = text;
      if (delta) onText(delta);
      return;
    }
    if (text.length > 12 && streamedText.endsWith(text)) return;
    streamedText += text;
    onText(text);
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const event of events) {
      const lines = event.split("\n");
      const eventType = lines
        .find((line) => line.startsWith("event:"))
        ?.slice(6)
        .trim();
      const dataLines = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());
      if (dataLines.length === 0) continue;
      const raw = dataLines.join("\n");
      if (raw === "[DONE]" || raw === "null") continue;

      try {
        const parsed = JSON.parse(raw) as unknown;
        extractStreamActions(parsed, eventType).forEach(emitAction);
        if (eventType === "error") {
          runError = extractStreamError(parsed) ?? "运行失败";
        }
        if (!eventType || eventType === "messages") {
          const text = extractMessageContent(parsed);
          if (text?.trim()) emitText(text);
        }
      } catch {
        // Ignore non-JSON SSE payloads.
      }
    }
  }

  for (const action of latestActions.values()) {
    if (action.status !== "running" || action.kind !== "tool") continue;
    emitAction({
      ...action,
      status: "completed",
      title: toolTitle(action.toolName, "completed"),
      detail: action.detail ?? "已完成",
    });
  }
  if (runError) throw new Error(runError);
}
