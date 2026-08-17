"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenIcon,
  ChevronDownIcon,
  DownloadIcon,
  FilesIcon,
  FileTextIcon,
  Loader2Icon,
  PaperclipIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SendIcon,
  Settings2Icon,
  SquareIcon,
  XIcon,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  startThreadRun,
  stopThreadRun,
  useActiveThreadRun,
} from "@/features/chat/active-thread-run";
import {
  createThread,
  downloadThreadArtifact,
  exportConversationDocx,
  getThreadMessages,
  listThreadArtifacts,
  patchThread,
  uploadFile,
} from "@/features/chat/api";
import type { ThreadArtifact } from "@/features/chat/api";
import { continuationRunContext } from "@/features/chat/continue-run";
import { ExecutionModeToggle } from "@/features/chat/execution-mode-toggle";
import { normalizeMessages } from "@/features/chat/message-utils";
import type { LocalMessage } from "@/features/chat/message-utils";
import { MessageList } from "@/features/chat/message-view";
import {
  summarizeThreadTitle,
  UNTITLED_DIRECT_THREAD_TITLE,
} from "@/features/chat/thread-title";
import { useExecutionMode } from "@/features/chat/use-execution-mode";
import {
  DEFAULT_WORD_FORMAT,
  WORD_FONT_OPTIONS,
} from "@/features/exports/word-format";
import type { WordFormatOptions } from "@/features/exports/word-format";
import { loadModels } from "@/features/settings/api";
import { formatDateTime } from "@/shared/lib/format";
import { createId } from "@/shared/lib/ids";

const quickPrompts = [
  {
    title: "检索政策指南",
    prompt:
      "请帮我检索并总结当前项目相关的申报政策指南，重点列出申报条件、材料清单和时间节点。",
    icon: BookOpenIcon,
  },
  {
    title: "撰写申报章节",
    prompt: "请帮我撰写申报书中的立项依据和技术路线，要求结构清晰、语言正式。",
    icon: FileTextIcon,
  },
  {
    title: "配置智能体",
    prompt:
      "请检查当前申报助手配置是否完整，并说明需要补充哪些模型、技能或 MCP 服务。",
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

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function ChatPage() {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [threadId, setThreadId] = useState(searchParams.get("thread") ?? "");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [artifactsPanelOpen, setArtifactsPanelOpen] = useState(true);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [wordFormat, setWordFormat] = useState<WordFormatOptions>({
    ...DEFAULT_WORD_FORMAT,
  });
  const [wordFormatCustomized, setWordFormatCustomized] = useState(false);
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

  const artifacts = useQuery({
    queryKey: ["thread-artifacts", threadId],
    queryFn: () => listThreadArtifacts(threadId),
    enabled: Boolean(threadId),
    refetchInterval: isRunning ? 2_000 : false,
    refetchOnWindowFocus: true,
  });

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      block: "end",
      behavior: "smooth",
    });
  }, [messages, isRunning]);

  async function ensureThread(titleSeed?: string) {
    if (threadId) return threadId;
    const nextThreadId = createId();
    await createThread(nextThreadId, {
      title: titleSeed
        ? summarizeThreadTitle(titleSeed)
        : UNTITLED_DIRECT_THREAD_TITLE,
      source: "chat-page",
      project_type: "government-project-declaration",
    });
    setThreadId(nextThreadId);
    window.history.replaceState(
      null,
      "",
      `/workspace/chat?thread=${encodeURIComponent(nextThreadId)}`,
    );
    await queryClient.invalidateQueries({ queryKey: ["threads"] });
    return nextThreadId;
  }

  function renameThreadFromFirstPrompt(
    currentThreadId: string,
    content: string,
  ) {
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
        output_style:
          "zh-CN government-project markdown, professional, no emoji",
        execution_mode: executionMode,
        workspace: "standalone-chat",
        ...(runContext ?? {}),
      },
      onComplete: async () => {
        await queryClient.invalidateQueries({
          queryKey: ["thread-messages", currentThreadId],
        });
        await queryClient.invalidateQueries({
          queryKey: ["thread-artifacts", currentThreadId],
        });
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
    startAssistantRun(
      currentThreadId,
      content,
      assistantId,
      nextMessages,
      continuationRunContext(content, messages),
    );
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
    if (!inserted)
      nextMessages.push({ id: assistantId, role: "assistant", content: "" });
    setMessages(nextMessages);
    startAssistantRun(
      currentThreadId,
      content,
      assistantId,
      nextMessages,
      continuationRunContext(content, messages),
    );
  }

  function deleteMessages(messageIds: string[]) {
    const deleted = new Set(messageIds);
    setMessages((current) =>
      current.filter((message) => !deleted.has(message.id)),
    );
  }

  async function stopRun() {
    if (threadId) await stopThreadRun(threadId);
  }

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const currentThreadId = await ensureThread(`附件：${file.name}`);
      return uploadFile(currentThreadId, file);
    },
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ["thread-messages", threadId],
      }),
  });

  const exportDocx = useMutation({
    mutationFn: (format: WordFormatOptions) =>
      exportConversationDocx({
        title: "智策对话记录",
        messages: messages.map((message) => ({
          role: message.role,
          content: message.content,
        })),
        wordFormat: format,
      }),
    onSuccess: (blob) => {
      downloadBlob(blob, "智策对话记录.docx");
      setExportDialogOpen(false);
    },
  });

  const downloadArtifact = useMutation({
    mutationFn: async (artifact: ThreadArtifact) => ({
      artifact,
      blob: await downloadThreadArtifact(artifact.download_url),
    }),
    onSuccess: ({ artifact, blob }) => downloadBlob(blob, artifact.name),
  });

  function updateWordFormat<Key extends keyof WordFormatOptions>(
    key: Key,
    value: WordFormatOptions[Key],
  ) {
    setWordFormat((current) => ({ ...current, [key]: value }));
    setWordFormatCustomized(true);
  }

  function openExportDialog() {
    exportDocx.reset();
    setWordFormat({ ...DEFAULT_WORD_FORMAT });
    setWordFormatCustomized(false);
    setExportDialogOpen(true);
  }

  const artifactItems = artifacts.data?.artifacts ?? [];

  return (
    <div
      className={`standalone-chat-layout${artifactsPanelOpen ? "" : "artifacts-collapsed"}`}
    >
      <main className="codex-main chat-canvas">
        <header className="main-head">
          <div>
            <div className="mh-title">智策对话</div>
          </div>
          <div className="mh-right">
            <button
              type="button"
              className={`ghost-btn${artifactsPanelOpen ? "active" : ""}`}
              aria-expanded={artifactsPanelOpen}
              aria-controls="chat-artifacts-panel"
              onClick={() => setArtifactsPanelOpen((current) => !current)}
            >
              <FilesIcon size={15} />
              产物{artifacts.data ? ` ${artifacts.data.total}` : ""}
            </button>
            <button
              type="button"
              className="ghost-btn"
              onClick={openExportDialog}
              disabled={!messages.length}
            >
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
                placeholder="输入申报问题…"
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
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={upload.isPending}
                  >
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
                  <select
                    value={selectedModel}
                    onChange={(event) => setSelectedModel(event.target.value)}
                  >
                    <option value="">默认模型</option>
                    {models.data?.models?.map((model) => (
                      <option key={model.name} value={model.name}>
                        {model.display_name ?? model.name}
                      </option>
                    ))}
                  </select>
                  <ExecutionModeToggle
                    value={executionMode}
                    disabled={isRunning}
                    onChange={setExecutionMode}
                  />
                  <button
                    type="button"
                    className={isRunning ? "send-btn stop" : "send-btn"}
                    aria-label={isRunning ? "暂停生成" : "发送消息"}
                    title={isRunning ? "暂停生成" : "发送消息"}
                    onClick={() => {
                      if (isRunning) void stopRun();
                      else void sendMessage();
                    }}
                  >
                    {isRunning ? (
                      <SquareIcon size={16} />
                    ) : remoteMessages.isFetching ? (
                      <Loader2Icon size={16} className="spin" />
                    ) : (
                      <SendIcon size={16} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {exportDialogOpen ? (
          <div
            className="modal-backdrop export-modal-backdrop"
            role="presentation"
            onMouseDown={() => {
              if (!exportDocx.isPending) setExportDialogOpen(false);
            }}
          >
            <div
              className="export-modal conversation-export-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="conversation-export-modal-title"
              onMouseDown={(event) => event.stopPropagation()}
            >
              <div className="modal-head">
                <div>
                  <span>Word 导出</span>
                  <h2 id="conversation-export-modal-title">导出对话记录</h2>
                  <p>导出前可调整正文、标题和段落格式。</p>
                </div>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="关闭导出设置"
                  disabled={exportDocx.isPending}
                  onClick={() => setExportDialogOpen(false)}
                >
                  <XIcon size={17} />
                </button>
              </div>

              <div className="export-modal-body">
                <section className="export-section">
                  <div className="export-section-head">
                    <div>
                      <h3>导出内容</h3>
                      <p>
                        当前对话中的 {messages.length} 条消息将合并为一个 Word
                        文件。
                      </p>
                    </div>
                  </div>

                  <details className="export-word-settings" open>
                    <summary>
                      <span>
                        <strong>Word 格式设置</strong>
                        <small>
                          {wordFormatCustomized
                            ? "已启用手动设置"
                            : "使用当前默认导出格式"}
                        </small>
                      </span>
                      <ChevronDownIcon size={17} aria-hidden="true" />
                    </summary>
                    <div className="export-word-settings-body">
                      <p>设置将应用于本次对话导出的正文、标题和段落。</p>
                      <div className="export-word-settings-grid">
                        <label>
                          <span>正文字体</span>
                          <select
                            value={wordFormat.bodyFont}
                            disabled={exportDocx.isPending}
                            onChange={(event) =>
                              updateWordFormat("bodyFont", event.target.value)
                            }
                          >
                            {WORD_FONT_OPTIONS.map((font) => (
                              <option key={font} value={font}>
                                {font}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>正文字号</span>
                          <select
                            value={wordFormat.bodyFontSizePt}
                            disabled={exportDocx.isPending}
                            onChange={(event) =>
                              updateWordFormat(
                                "bodyFontSizePt",
                                Number(event.target.value),
                              )
                            }
                          >
                            <option value={10.5}>五号（10.5 磅）</option>
                            <option value={12}>小四（12 磅）</option>
                            <option value={14}>四号（14 磅）</option>
                            <option value={15}>小三（15 磅）</option>
                            <option value={16}>三号（16 磅）</option>
                          </select>
                        </label>
                        <label>
                          <span>行间距</span>
                          <select
                            value={wordFormat.lineSpacing}
                            disabled={exportDocx.isPending}
                            onChange={(event) =>
                              updateWordFormat(
                                "lineSpacing",
                                Number(event.target.value),
                              )
                            }
                          >
                            <option value={1}>单倍行距</option>
                            <option value={1.25}>1.25 倍行距</option>
                            <option value={1.5}>1.5 倍行距</option>
                            <option value={2}>2 倍行距</option>
                          </select>
                        </label>
                        <label>
                          <span>标题字体</span>
                          <select
                            value={wordFormat.headingFont}
                            disabled={exportDocx.isPending}
                            onChange={(event) =>
                              updateWordFormat(
                                "headingFont",
                                event.target.value,
                              )
                            }
                          >
                            {WORD_FONT_OPTIONS.map((font) => (
                              <option key={font} value={font}>
                                {font}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>标题起始等级</span>
                          <select
                            value={wordFormat.headingStartLevel}
                            disabled={exportDocx.isPending}
                            onChange={(event) =>
                              updateWordFormat(
                                "headingStartLevel",
                                Number(event.target.value),
                              )
                            }
                          >
                            <option value={1}>一级标题</option>
                            <option value={2}>二级标题</option>
                            <option value={3}>三级标题</option>
                          </select>
                        </label>
                      </div>
                      <button
                        type="button"
                        className="export-word-settings-reset"
                        disabled={exportDocx.isPending || !wordFormatCustomized}
                        onClick={() => {
                          setWordFormat({ ...DEFAULT_WORD_FORMAT });
                          setWordFormatCustomized(false);
                        }}
                      >
                        <RotateCcwIcon size={14} />
                        恢复默认格式
                      </button>
                    </div>
                  </details>
                </section>
              </div>

              <div className="export-modal-foot">
                <span
                  className={exportDocx.isError ? "export-error" : undefined}
                >
                  {exportDocx.isError
                    ? exportDocx.error instanceof Error
                      ? exportDocx.error.message
                      : "导出失败，请稍后重试。"
                    : "确认格式后开始生成 Word 文件"}
                </span>
                <button
                  type="button"
                  className="primary-btn"
                  disabled={exportDocx.isPending}
                  onClick={() => exportDocx.mutate(wordFormat)}
                >
                  {exportDocx.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <DownloadIcon size={14} />
                  )}
                  {exportDocx.isPending ? "导出中" : "导出 Word"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </main>

      {artifactsPanelOpen ? (
        <aside
          id="chat-artifacts-panel"
          className="chat-artifacts-panel"
          aria-label="当前对话产物"
        >
          <div className="chat-artifacts-head">
            <div>
              <strong>产物</strong>
              <span>{artifacts.data?.total ?? 0} 个文件</span>
            </div>
            <div className="chat-artifacts-actions">
              <button
                type="button"
                aria-label="刷新产物列表"
                title="刷新产物列表"
                disabled={!threadId || artifacts.isFetching}
                onClick={() => void artifacts.refetch()}
              >
                <RefreshCwIcon
                  size={15}
                  className={artifacts.isFetching ? "spin" : undefined}
                />
              </button>
              <button
                type="button"
                aria-label="关闭产物面板"
                title="关闭产物面板"
                onClick={() => setArtifactsPanelOpen(false)}
              >
                <XIcon size={16} />
              </button>
            </div>
          </div>

          {isRunning ? (
            <div className="chat-artifacts-running">
              <Loader2Icon size={14} className="spin" />
              智能体运行中，产物列表会自动更新
            </div>
          ) : null}

          <div className="chat-artifacts-list">
            {!threadId ? (
              <div className="chat-artifacts-empty">
                <FilesIcon size={24} />
                <span>发送消息后，当前对话生成的文件会显示在这里。</span>
              </div>
            ) : artifacts.isLoading ? (
              <div className="chat-artifacts-empty">
                <Loader2Icon size={20} className="spin" />
                <span>正在读取产物</span>
              </div>
            ) : artifacts.isError ? (
              <div className="chat-artifacts-empty error">
                <span>
                  {artifacts.error instanceof Error
                    ? artifacts.error.message
                    : "产物列表加载失败。"}
                </span>
                <button type="button" onClick={() => void artifacts.refetch()}>
                  重试
                </button>
              </div>
            ) : artifactItems.length === 0 ? (
              <div className="chat-artifacts-empty">
                <FilesIcon size={24} />
                <span>当前对话还没有生成文件。</span>
              </div>
            ) : (
              artifactItems.map((artifact) => {
                const downloading =
                  downloadArtifact.isPending &&
                  downloadArtifact.variables?.path === artifact.path;
                return (
                  <article key={artifact.path} className="chat-artifact-item">
                    <div className="chat-artifact-icon">
                      <FileTextIcon size={17} />
                    </div>
                    <div className="chat-artifact-info">
                      <strong title={artifact.name}>{artifact.name}</strong>
                      <span title={artifact.relative_path}>
                        {artifact.relative_path}
                      </span>
                      <small>
                        {formatFileSize(artifact.size)} ·{" "}
                        {formatDateTime(artifact.updated_at)}
                      </small>
                    </div>
                    <button
                      type="button"
                      className="chat-artifact-download"
                      aria-label={`下载 ${artifact.name}`}
                      title={`下载 ${artifact.name}`}
                      disabled={downloadArtifact.isPending}
                      onClick={() => downloadArtifact.mutate(artifact)}
                    >
                      {downloading ? (
                        <Loader2Icon size={15} className="spin" />
                      ) : (
                        <DownloadIcon size={15} />
                      )}
                    </button>
                  </article>
                );
              })
            )}
          </div>

          {artifacts.data?.truncated ? (
            <div className="chat-artifacts-note">
              文件较多，当前显示最近的 {artifactItems.length} 个产物。
            </div>
          ) : downloadArtifact.isError ? (
            <div className="chat-artifacts-note error">
              {downloadArtifact.error instanceof Error
                ? downloadArtifact.error.message
                : "下载失败，请稍后重试。"}
            </div>
          ) : (
            <div className="chat-artifacts-note">
              这里仅显示当前对话生成的文件，可逐个下载。
            </div>
          )}
        </aside>
      ) : null}
    </div>
  );
}
