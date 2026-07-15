"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenIcon,
  DownloadIcon,
  FileTextIcon,
  Loader2Icon,
  PaperclipIcon,
  SendIcon,
  Settings2Icon,
  SquareIcon,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  startThreadRun,
  stopThreadRun,
  useActiveThreadRun,
} from "@/features/chat/active-thread-run";
import {
  createThread,
  exportConversationDocx,
  getThreadMessages,
  patchThread,
  uploadFile,
} from "@/features/chat/api";
import { continuationRunContext } from "@/features/chat/continue-run";
import { ExecutionModeToggle } from "@/features/chat/execution-mode-toggle";
import { normalizeMessages } from "@/features/chat/message-utils";
import type { LocalMessage } from "@/features/chat/message-utils";
import { MessageList } from "@/features/chat/message-view";
import { summarizeThreadTitle, UNTITLED_DIRECT_THREAD_TITLE } from "@/features/chat/thread-title";
import { useExecutionMode } from "@/features/chat/use-execution-mode";
import { loadModels } from "@/features/settings/api";
import { createId } from "@/shared/lib/ids";

const quickPrompts = [
  {
    title: "检索政策指南",
    desc: "查找申报指南、管理办法和截止时间",
    prompt: "请帮我检索并总结当前项目相关的申报政策指南，重点列出申报条件、材料清单和时间节点。",
    icon: BookOpenIcon,
  },
  {
    title: "撰写申报章节",
    desc: "生成立项依据、技术路线、创新点",
    prompt: "请帮我撰写申报书中的立项依据和技术路线，要求结构清晰、语言正式。",
    icon: FileTextIcon,
  },
  {
    title: "配置智能体",
    desc: "检查模型、技能、MCP 是否可用",
    prompt: "请检查当前申报助手配置是否完整，并说明需要补充哪些模型、技能或 MCP 服务。",
    icon: Settings2Icon,
  },
];

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function ChatPage() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState(searchParams.get("thread") ?? "");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [executionMode, setExecutionMode] = useExecutionMode();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const activeRun = useActiveThreadRun(threadId);

  useEffect(() => {
    setThreadId(searchParams.get("thread") ?? "");
  }, [searchParams]);

  const remoteMessages = useQuery({
    queryKey: ["thread-messages", threadId],
    queryFn: () => getThreadMessages(threadId),
    enabled: Boolean(threadId),
  });

  useEffect(() => {
    if (activeRun) {
      setMessages(activeRun.messages);
      return;
    }
    if (remoteMessages.data) {
      setMessages(normalizeMessages(remoteMessages.data));
      return;
    }
    if (!threadId) setMessages([]);
  }, [activeRun, remoteMessages.data, threadId]);

  const models = useQuery({ queryKey: ["models"], queryFn: loadModels });

  useEffect(() => {
    const first = models.data?.models?.[0]?.name;
    if (first && !selectedModel) setSelectedModel(first);
  }, [models.data, selectedModel]);

  const isRunning = activeRun?.status === "running";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages, isRunning]);

  async function ensureThread(titleSeed?: string) {
    if (threadId) return threadId;
    const nextThreadId = createId();
    await createThread(nextThreadId, {
      title: titleSeed ? summarizeThreadTitle(titleSeed) : UNTITLED_DIRECT_THREAD_TITLE,
      source: "chat-page",
      project_type: "government-project-declaration",
    });
    setThreadId(nextThreadId);
    window.history.replaceState(null, "", `/workspace/chat?thread=${encodeURIComponent(nextThreadId)}`);
    await queryClient.invalidateQueries({ queryKey: ["threads"] });
    return nextThreadId;
  }

  function renameThreadFromFirstPrompt(currentThreadId: string, content: string) {
    const title = summarizeThreadTitle(content);
    void patchThread(currentThreadId, { title, auto_title: true })
      .then(() => queryClient.invalidateQueries({ queryKey: ["threads"] }))
      .catch(() => undefined);
  }

  function startAssistantRun(
    currentThreadId: string,
    content: string,
    assistantId: string,
    nextMessages: LocalMessage[],
    runContext?: Record<string, unknown>,
  ) {
    startThreadRun({
      threadId: currentThreadId,
      content,
      assistantId,
      messages: nextMessages,
      context: {
        model_name: selectedModel || undefined,
        output_language: "zh-CN",
        output_style: "zh-CN government-project markdown, professional, no emoji",
        execution_mode: executionMode,
        workspace: "standalone-chat",
        ...(runContext ?? {}),
      },
      onComplete: async () => {
        await queryClient.invalidateQueries({ queryKey: ["thread-messages", currentThreadId] });
        await queryClient.invalidateQueries({ queryKey: ["threads"] });
      },
    });
  }

  async function sendMessage(prompt = input) {
    const content = prompt.trim();
    if (!content || isRunning) return;
    const shouldRename = messages.every((message) => message.role !== "user");
    const currentThreadId = await ensureThread(content);
    setInput("");

    const userMessage: LocalMessage = { id: createId(), role: "user", content };
    const assistantId = createId();
    const nextMessages: LocalMessage[] = [
      ...messages,
      userMessage,
      { id: assistantId, role: "assistant", content: "" },
    ];
    setMessages(nextMessages);

    if (shouldRename) renameThreadFromFirstPrompt(currentThreadId, content);
    startAssistantRun(currentThreadId, content, assistantId, nextMessages, continuationRunContext(content, messages));
  }

  async function regenerateAnswer(prompt: string, assistantIds: string[]) {
    const content = prompt.trim();
    if (!content || isRunning) return;
    const currentThreadId = await ensureThread(content);
    const assistantId = assistantIds[0] ?? createId();
    let inserted = false;
    const nextMessages = messages.flatMap((message) => {
      if (!assistantIds.includes(message.id)) return [message];
      if (inserted) return [];
      inserted = true;
      return [{ id: assistantId, role: "assistant" as const, content: "" }];
    });
    if (!inserted) nextMessages.push({ id: assistantId, role: "assistant", content: "" });
    setMessages(nextMessages);
    startAssistantRun(currentThreadId, content, assistantId, nextMessages, continuationRunContext(content, messages));
  }

  function deleteMessages(messageIds: string[]) {
    const deleted = new Set(messageIds);
    setMessages((current) => current.filter((message) => !deleted.has(message.id)));
  }

  async function stopRun() {
    if (threadId) await stopThreadRun(threadId);
  }

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const currentThreadId = await ensureThread(`附件：${file.name}`);
      return uploadFile(currentThreadId, file);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["thread-messages", threadId] }),
  });

  const exportDocx = useMutation({
    mutationFn: () =>
      exportConversationDocx({
        title: "智策对话记录",
        messages: messages.map((message) => ({ role: message.role, content: message.content })),
      }),
    onSuccess: (blob) => downloadBlob(blob, "智策对话记录.docx"),
  });

  const headerTags = useMemo(
    () => [
      threadId ? `线程 ${threadId.slice(0, 8)}` : "未创建线程",
      selectedModel || "默认模型",
    ],
    [selectedModel, threadId],
  );

  return (
    <main className="codex-main chat-canvas">
      <header className="main-head">
        <div>
          <div className="mh-title">智策对话</div>
          <div className="mh-breadcrumb">项目申报 / 智能体协作</div>
        </div>
        <div className="mh-right">
          {headerTags.map((tag) => (
            <span key={tag} className="tag muted">
              {tag}
            </span>
          ))}
          <button type="button" className="ghost-btn" onClick={() => exportDocx.mutate()} disabled={!messages.length}>
            <DownloadIcon size={15} />
            导出
          </button>
        </div>
      </header>

      <div className="main-body">
        {messages.length === 0 ? (
          <div className="welcome-panel">
            <div className="welcome-emblem">策</div>
            <h1>开启新的项目申报协作</h1>
            <p>直接描述申报需求，或选择一个快捷入口。系统会创建线程并进入流式对话。</p>
            <div className="quick-grid">
              {quickPrompts.map((card) => {
                const Icon = card.icon;
                return (
                  <button
                    key={card.title}
                    type="button"
                    className="quick-card"
                    onClick={() => void sendMessage(card.prompt)}
                  >
                    <Icon className="qc-icon" size={22} />
                    <div className="qc-title">{card.title}</div>
                    <div className="qc-desc">{card.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          <MessageList
            messages={messages}
            endRef={messagesEndRef}
            isRunning={isRunning}
            onRegenerate={regenerateAnswer}
            onDeleteMessages={deleteMessages}
          />
        )}

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              value={input}
              rows={2}
              placeholder="输入消息，与智策助手协作推进项目..."
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <div className="composer-bar">
              <div className="cb-left">
                <button type="button" onClick={() => fileInputRef.current?.click()} disabled={upload.isPending}>
                  <PaperclipIcon size={15} />
                  {upload.isPending ? "上传中" : "附件"}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) upload.mutate(file);
                    event.currentTarget.value = "";
                  }}
                />
              </div>
              <div className="cb-right">
                <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                  <option value="">默认模型</option>
                  {models.data?.models?.map((model) => (
                    <option key={model.name} value={model.name}>
                      {model.display_name ?? model.name}
                    </option>
                  ))}
                </select>
                <ExecutionModeToggle value={executionMode} disabled={isRunning} onChange={setExecutionMode} />
                <button
                  type="button"
                  className={`send-btn${isRunning ? " stop" : ""}`}
                  aria-label={isRunning ? "暂停生成" : "发送消息"}
                  title={isRunning ? "暂停生成" : "发送消息"}
                  onClick={() => {
                    if (isRunning) void stopRun();
                    else void sendMessage();
                  }}
                >
                  {isRunning ? (
                    <SquareIcon size={16} />
                  ) : (
                    remoteMessages.isFetching ? <Loader2Icon size={16} className="spin" /> : <SendIcon size={16} />
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
