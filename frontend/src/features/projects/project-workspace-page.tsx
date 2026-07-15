"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DownloadIcon,
  FileIcon,
  FolderIcon,
  FolderOpenIcon,
  ImageIcon,
  Loader2Icon,
  PaperclipIcon,
  PanelRightCloseIcon,
  PanelRightOpenIcon,
  PencilIcon,
  RefreshCwIcon,
  SaveIcon,
  SendIcon,
  SquareIcon,
  Trash2Icon,
  XIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  startThreadRun,
  stopThreadRun,
  useActiveThreadRun,
} from "@/features/chat/active-thread-run";
import {
  createThread,
  getThreadMessages,
  patchThread,
  searchThreads,
} from "@/features/chat/api";
import { continuationRunContext } from "@/features/chat/continue-run";
import { ExecutionModeToggle } from "@/features/chat/execution-mode-toggle";
import { MarkdownRenderer } from "@/features/chat/markdown-renderer";
import { normalizeMessages } from "@/features/chat/message-utils";
import type { LocalMessage } from "@/features/chat/message-utils";
import { MessageList } from "@/features/chat/message-view";
import {
  summarizeThreadTitle,
  UNTITLED_PROJECT_THREAD_TITLE,
} from "@/features/chat/thread-title";
import { useExecutionMode } from "@/features/chat/use-execution-mode";
import {
  deleteProjectFile,
  downloadProjectFile,
  exportProjectFilesDocx,
  getProject,
  getProjectDirectory,
  listProjectFiles,
  readProjectFile,
  selectProjectDirectory,
  updateProjectDirectory,
  uploadProjectFiles,
  writeProjectFile,
} from "@/features/projects/api";
import type { ProjectFileNode } from "@/features/projects/api";
import { loadModels } from "@/features/settings/api";
import { formatDateTime } from "@/shared/lib/format";
import { createId } from "@/shared/lib/ids";

interface ProjectWorkspacePageProps {
  projectId: string;
  initialThreadId?: string;
}

const categoryLabel: Record<ProjectFileNode["category"], string> = {
  draft: "申报书",
  input: "附件",
  output: "输出",
  version: "版本",
  other: "其他",
};

const RIGHT_SIDEBAR_WIDTH_STORAGE_KEY = "project-sidebar-right-width";
const RIGHT_SIDEBAR_COLLAPSED_STORAGE_KEY = "project-sidebar-right-collapsed";
const RIGHT_SIDEBAR_DEFAULT_WIDTH = 340;
const RIGHT_SIDEBAR_MIN_WIDTH = 280;
const RIGHT_SIDEBAR_MAX_WIDTH = 620;

function clampRightSidebarWidth(width: number) {
  return Math.min(
    RIGHT_SIDEBAR_MAX_WIDTH,
    Math.max(RIGHT_SIDEBAR_MIN_WIDTH, Math.round(width)),
  );
}

function getStoredRightSidebarWidth() {
  if (typeof window === "undefined") return null;
  try {
    const value = Number(
      window.localStorage.getItem(RIGHT_SIDEBAR_WIDTH_STORAGE_KEY),
    );
    return Number.isFinite(value) ? clampRightSidebarWidth(value) : null;
  } catch {
    return null;
  }
}

function storeRightSidebarWidth(width: number) {
  try {
    window.localStorage.setItem(RIGHT_SIDEBAR_WIDTH_STORAGE_KEY, String(width));
  } catch {
    // Width persistence is optional; dragging should still work for the current session.
  }
}

function getStoredRightSidebarCollapsed() {
  if (typeof window === "undefined") return false;
  try {
    return (
      window.localStorage.getItem(RIGHT_SIDEBAR_COLLAPSED_STORAGE_KEY) ===
      "true"
    );
  } catch {
    return false;
  }
}

function storeRightSidebarCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(
      RIGHT_SIDEBAR_COLLAPSED_STORAGE_KEY,
      String(collapsed),
    );
  } catch {
    // Collapsed state persistence is optional.
  }
}

function fileSize(size?: number) {
  if (!size) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function isExportableFile(file: ProjectFileNode) {
  return /\.(md|markdown|txt)$/i.test(file.name);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ProjectWorkspacePage({
  projectId,
  initialThreadId,
}: ProjectWorkspacePageProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState(
    initialThreadId ?? "",
  );
  const [selectedFile, setSelectedFile] = useState<ProjectFileNode | null>(
    null,
  );
  const [rightTab, setRightTab] = useState<"tree" | "preview">("tree");
  const [rightSidebarWidth, setRightSidebarWidth] = useState(
    RIGHT_SIDEBAR_DEFAULT_WIDTH,
  );
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(false);
  const [resizingRightSidebar, setResizingRightSidebar] = useState(false);
  const [fileDialogOpen, setFileDialogOpen] = useState(false);
  const [fileEditing, setFileEditing] = useState(false);
  const [fileDraftContent, setFileDraftContent] = useState("");
  const [directoryDialogOpen, setDirectoryDialogOpen] = useState(false);
  const [directoryDraftPath, setDirectoryDraftPath] = useState("");
  const [directoryNotice, setDirectoryNotice] = useState("");
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [exportMode, setExportMode] = useState<"merged" | "separate">("merged");
  const [includeImages, setIncludeImages] = useState(false);
  const [exportSelectedIds, setExportSelectedIds] = useState<Set<string>>(
    new Set(),
  );
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [executionMode, setExecutionMode] = useExecutionMode();
  const activeRun = useActiveThreadRun(selectedThreadId);

  useEffect(() => {
    const storedWidth = getStoredRightSidebarWidth();
    if (storedWidth) setRightSidebarWidth(storedWidth);
    setRightSidebarCollapsed(getStoredRightSidebarCollapsed());
    return () => document.documentElement.classList.remove("sidebar-resizing");
  }, []);

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  const projectDirectory = useQuery({
    queryKey: ["project-directory", projectId],
    queryFn: () => getProjectDirectory(projectId),
  });
  const files = useQuery({
    queryKey: ["project-files", projectId],
    queryFn: () => listProjectFiles(projectId),
  });
  const threads = useQuery({
    queryKey: ["project-threads", projectId],
    queryFn: () => searchThreads(80, { project_id: projectId }),
  });
  const remoteMessages = useQuery({
    queryKey: ["thread-messages", selectedThreadId],
    queryFn: () => getThreadMessages(selectedThreadId),
    enabled: Boolean(selectedThreadId),
  });
  const fileContent = useQuery({
    queryKey: ["project-file-content", projectId, selectedFile?.id],
    queryFn: () => readProjectFile(projectId, selectedFile!),
    enabled: Boolean(selectedFile),
  });
  const models = useQuery({ queryKey: ["models"], queryFn: loadModels });

  useEffect(() => {
    if (initialThreadId) setSelectedThreadId(initialThreadId);
  }, [initialThreadId]);

  useEffect(() => {
    if (!initialThreadId && !selectedThreadId && threads.data?.[0]) {
      setSelectedThreadId(threads.data[0].thread_id);
    }
  }, [initialThreadId, selectedThreadId, threads.data]);

  useEffect(() => {
    if (activeRun) {
      setMessages(activeRun.messages);
      return;
    }
    if (remoteMessages.data) {
      setMessages(normalizeMessages(remoteMessages.data));
      return;
    }
    if (!selectedThreadId) setMessages([]);
  }, [activeRun, remoteMessages.data, selectedThreadId]);

  useEffect(() => {
    const firstFile = files.data?.files?.[0];
    if (!selectedFile && firstFile) setSelectedFile(firstFile);
  }, [files.data, selectedFile]);

  useEffect(() => {
    if (!fileEditing) setFileDraftContent(fileContent.data?.content ?? "");
  }, [fileContent.data?.content, fileEditing, selectedFile?.id]);

  useEffect(() => {
    const first = models.data?.models?.[0]?.name;
    if (first && !selectedModel) setSelectedModel(first);
  }, [models.data, selectedModel]);

  useEffect(() => {
    if (!directoryDialogOpen) return;
    setDirectoryDraftPath(
      projectDirectory.data?.root_path ?? project.data?.root_path ?? "",
    );
  }, [
    directoryDialogOpen,
    project.data?.root_path,
    projectDirectory.data?.root_path,
  ]);

  const groupedFiles = useMemo(() => {
    const groups = new Map<ProjectFileNode["category"], ProjectFileNode[]>();
    for (const file of files.data?.files ?? []) {
      groups.set(file.category, [...(groups.get(file.category) ?? []), file]);
    }
    return Array.from(groups.entries());
  }, [files.data]);

  const exportableFiles = useMemo(
    () => (files.data?.files ?? []).filter(isExportableFile),
    [files.data],
  );

  const exportableGroups = useMemo(() => {
    const groups = new Map<ProjectFileNode["category"], ProjectFileNode[]>();
    for (const file of exportableFiles) {
      groups.set(file.category, [...(groups.get(file.category) ?? []), file]);
    }
    return Array.from(groups.entries());
  }, [exportableFiles]);

  const selectedExportFiles = useMemo(
    () => exportableFiles.filter((file) => exportSelectedIds.has(file.id)),
    [exportSelectedIds, exportableFiles],
  );

  async function ensureThread(titleSeed?: string) {
    if (selectedThreadId) return selectedThreadId;
    const nextThreadId = createId();
    await createThread(nextThreadId, {
      project_id: projectId,
      project_name: project.data?.name,
      title: titleSeed
        ? summarizeThreadTitle(titleSeed, UNTITLED_PROJECT_THREAD_TITLE)
        : UNTITLED_PROJECT_THREAD_TITLE,
      source: "project-workspace",
    });
    setSelectedThreadId(nextThreadId);
    router.replace(
      `/workspace/projects/${encodeURIComponent(projectId)}/threads/${encodeURIComponent(nextThreadId)}`,
    );
    await queryClient.invalidateQueries({
      queryKey: ["project-threads", projectId],
    });
    await queryClient.invalidateQueries({ queryKey: ["threads"] });
    return nextThreadId;
  }

  function renameThreadFromFirstPrompt(
    currentThreadId: string,
    content: string,
  ) {
    const title = summarizeThreadTitle(content, UNTITLED_PROJECT_THREAD_TITLE);
    void patchThread(currentThreadId, { title, auto_title: true })
      .then(async () => {
        await queryClient.invalidateQueries({
          queryKey: ["project-threads", projectId],
        });
        await queryClient.invalidateQueries({ queryKey: ["threads"] });
      })
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
        project_id: projectId,
        project_name: project.data?.name,
        applicant_id:
          typeof project.data?.metadata?.applicant_id === "string"
            ? project.data.metadata.applicant_id
            : "default",
        model_name: selectedModel || undefined,
        execution_mode: executionMode,
        ...(runContext ?? {}),
      },
      onComplete: async () => {
        await queryClient.invalidateQueries({
          queryKey: ["thread-messages", currentThreadId],
        });
        await queryClient.invalidateQueries({
          queryKey: ["project-files", projectId],
        });
        await queryClient.invalidateQueries({
          queryKey: ["project-summary", projectId],
        });
        await queryClient.invalidateQueries({
          queryKey: ["project-threads", projectId],
        });
        await queryClient.invalidateQueries({ queryKey: ["threads"] });
      },
    });
  }

  async function sendMessage() {
    const content = input.trim();
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
    if (selectedThreadId) await stopThreadRun(selectedThreadId);
  }

  const upload = useMutation({
    mutationFn: (uploadFiles: File[]) =>
      uploadProjectFiles(projectId, uploadFiles, "inputs"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["project-files", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-summary", projectId],
      });
    },
  });

  const saveProjectDirectory = useMutation({
    mutationFn: (rootPath: string | null) =>
      updateProjectDirectory(projectId, { root_path: rootPath, create: true }),
    onSuccess: async (directory) => {
      setDirectoryDraftPath(directory.root_path);
      setDirectoryNotice("项目目录已更新");
      await queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      await queryClient.invalidateQueries({
        queryKey: ["project-directory", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-files", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-summary", projectId],
      });
    },
  });

  const selectDirectory = useMutation({
    mutationFn: () => selectProjectDirectory(projectId),
    onSuccess: (directory) => {
      if (directory.selected && directory.root_path) {
        setDirectoryDraftPath(directory.root_path);
        setDirectoryNotice("已选择目录，保存后生效");
        return;
      }
      setDirectoryNotice("未选择目录");
    },
  });

  const removeFile = useMutation({
    mutationFn: (file: ProjectFileNode) => deleteProjectFile(projectId, file),
    onSuccess: async () => {
      setSelectedFile(null);
      setFileDialogOpen(false);
      setFileEditing(false);
      await queryClient.invalidateQueries({
        queryKey: ["project-files", projectId],
      });
    },
  });

  const saveFile = useMutation({
    mutationFn: ({
      file,
      content,
    }: {
      file: ProjectFileNode;
      content: string;
    }) => writeProjectFile(projectId, file, content),
    onSuccess: async (updatedFile, variables) => {
      setSelectedFile((current) =>
        current?.id === variables.file.id ? updatedFile : current,
      );
      setFileEditing(false);
      await queryClient.invalidateQueries({
        queryKey: ["project-files", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-summary", projectId],
      });
      await queryClient.invalidateQueries({
        queryKey: ["project-file-content", projectId, variables.file.id],
      });
    },
  });

  const exportFiles = useMutation({
    mutationFn: ({
      items,
      mode,
      includeImages,
    }: {
      items: ProjectFileNode[];
      mode: "merged" | "separate";
      includeImages: boolean;
    }) =>
      exportProjectFilesDocx(projectId, items, mode, project.data?.name, {
        includeImages,
        modelName: selectedModel.trim() ? selectedModel : undefined,
      }),
    onSuccess: (blob, variables) => {
      const baseName = project.data?.name?.trim() ?? "项目文件导出";
      downloadBlob(
        blob,
        variables.mode === "merged" ? `${baseName}.docx` : `${baseName}.zip`,
      );
      setExportDialogOpen(false);
    },
  });

  const exportErrorMessage =
    exportFiles.error instanceof Error
      ? exportFiles.error.message
      : "导出失败，请稍后重试。";
  const directoryErrorMessage =
    saveProjectDirectory.error instanceof Error
      ? saveProjectDirectory.error.message
      : selectDirectory.error instanceof Error
        ? selectDirectory.error.message
        : "目录操作失败，请检查路径。";
  const directoryPending =
    saveProjectDirectory.isPending || selectDirectory.isPending;

  const isRunning = activeRun?.status === "running";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      block: "end",
      behavior: "smooth",
    });
  }, [messages, isRunning, selectedThreadId]);

  function handleRightSidebarResizePointerDown(
    event: ReactPointerEvent<HTMLButtonElement>,
  ) {
    event.preventDefault();
    if (rightSidebarCollapsed) return;

    const startX = event.clientX;
    const startWidth = rightSidebarWidth;
    let nextWidth = startWidth;

    setResizingRightSidebar(true);
    document.documentElement.classList.add("sidebar-resizing");

    const handlePointerMove = (moveEvent: PointerEvent) => {
      nextWidth = clampRightSidebarWidth(
        startWidth + startX - moveEvent.clientX,
      );
      setRightSidebarWidth(nextWidth);
    };

    const finishResize = () => {
      setResizingRightSidebar(false);
      document.documentElement.classList.remove("sidebar-resizing");
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", finishResize);
      window.removeEventListener("pointercancel", finishResize);
      storeRightSidebarWidth(nextWidth);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", finishResize);
    window.addEventListener("pointercancel", finishResize);
  }

  function toggleRightSidebarCollapsed(collapsed: boolean) {
    setRightSidebarCollapsed(collapsed);
    storeRightSidebarCollapsed(collapsed);
  }

  function openFileDialog(file: ProjectFileNode) {
    setSelectedFile(file);
    setFileEditing(false);
    setFileDraftContent("");
    setFileDialogOpen(true);
  }

  function openDirectoryDialog() {
    saveProjectDirectory.reset();
    selectDirectory.reset();
    setDirectoryNotice("");
    setDirectoryDraftPath(
      projectDirectory.data?.root_path ?? project.data?.root_path ?? "",
    );
    setDirectoryDialogOpen(true);
  }

  function saveDirectoryPath(rootPath: string | null) {
    saveProjectDirectory.reset();
    selectDirectory.reset();
    setDirectoryNotice("");
    saveProjectDirectory.mutate(rootPath);
  }

  function handleFileEditSave() {
    if (!selectedFile || fileContent.isLoading) return;
    if (!fileEditing) {
      setFileDraftContent(fileContent.data?.content ?? "");
      setFileEditing(true);
      return;
    }
    saveFile.mutate({ file: selectedFile, content: fileDraftContent });
  }

  function openExportDialog() {
    const preferredCategory = selectedFile?.category ?? "output";
    const scopedFiles = exportableFiles.filter(
      (file) => file.category === preferredCategory,
    );
    const defaults = scopedFiles.length > 0 ? scopedFiles : exportableFiles;
    exportFiles.reset();
    setExportSelectedIds(new Set(defaults.map((file) => file.id)));
    setExportMode("merged");
    setIncludeImages(false);
    setExportDialogOpen(true);
  }

  function toggleExportFile(fileId: string) {
    setExportSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  }

  const projectGridStyle = {
    "--right-w": `${rightSidebarWidth}px`,
  } as CSSProperties & { "--right-w": string };

  const selectedFileContent = fileContent.data?.content ?? "";
  const displayedFileContent = fileEditing
    ? fileDraftContent
    : selectedFileContent;
  const canEditSelectedFile =
    Boolean(selectedFile) && !fileContent.isLoading && !fileContent.isError;

  return (
    <>
      <div
        className={`project-page-grid${rightSidebarCollapsed ? "right-collapsed" : ""}${resizingRightSidebar ? "resizing-right" : ""}`}
        style={projectGridStyle}
      >
        <main className="codex-main chat-canvas">
          <header className="main-head">
            <div>
              <div className="mh-title">
                {project.data?.name ?? "项目工作台"}
              </div>
              <div className="mh-breadcrumb">
                {project.data?.status ?? "进行中"} / 更新于{" "}
                {formatDateTime(project.data?.updated_at)}
              </div>
            </div>
          </header>

          <div className="main-body">
            {messages.length === 0 ? (
              <div className="welcome-panel compact">
                <div className="welcome-emblem">策</div>
                <h1>围绕当前项目开始协作</h1>
                <p>
                  可以让智策检索政策、梳理技术路线、生成预算说明，或根据右侧材料完善申报书。
                </p>
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
                    <button type="button" onClick={openDirectoryDialog}>
                      {projectDirectory.isFetching ? (
                        <Loader2Icon size={15} className="spin" />
                      ) : (
                        <FolderOpenIcon size={15} />
                      )}
                      项目工作区
                    </button>
                    <button
                      type="button"
                      onClick={() => uploadInputRef.current?.click()}
                    >
                      <PaperclipIcon size={15} />
                      上传材料
                    </button>
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
                      className={`send-btn${isRunning ? "stop" : ""}`}
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
                        <SendIcon size={16} />
                      )}
                    </button>
                  </div>
                </div>
                <input
                  ref={uploadInputRef}
                  type="file"
                  multiple
                  hidden
                  onChange={(event) => {
                    const uploadFiles = Array.from(event.target.files ?? []);
                    if (uploadFiles.length) upload.mutate(uploadFiles);
                    event.currentTarget.value = "";
                  }}
                />
              </div>
            </div>
          </div>
        </main>

        <aside
          className={`sidebar-right${rightSidebarCollapsed ? "collapsed" : ""}`}
        >
          {rightSidebarCollapsed ? (
            <button
              type="button"
              className="sidebar-right-rail-btn"
              aria-label="展开右侧文件区"
              title="展开右侧文件区"
              onClick={() => toggleRightSidebarCollapsed(false)}
            >
              <PanelRightOpenIcon size={16} />
            </button>
          ) : null}
          <button
            type="button"
            className="sidebar-right-resize-handle"
            aria-label="调整右侧栏宽度"
            title="拖动调整右侧栏宽度"
            onDoubleClick={() => {
              setRightSidebarWidth(RIGHT_SIDEBAR_DEFAULT_WIDTH);
              storeRightSidebarWidth(RIGHT_SIDEBAR_DEFAULT_WIDTH);
            }}
            onPointerDown={handleRightSidebarResizePointerDown}
          />
          <div className="sr-head">
            <div className="sr-tabs">
              <button
                type="button"
                className={rightTab === "tree" ? "active" : ""}
                onClick={() => setRightTab("tree")}
              >
                文件树
              </button>
              <button
                type="button"
                className={exportDialogOpen ? "active" : ""}
                onClick={openExportDialog}
              >
                导出
              </button>
            </div>
            <div className="sr-actions">
              <button
                type="button"
                className="icon-btn"
                onClick={() => files.refetch()}
                title="刷新文件"
              >
                {files.isFetching ? (
                  <Loader2Icon size={15} className="spin" />
                ) : (
                  <RefreshCwIcon size={15} />
                )}
              </button>
              <button
                type="button"
                className="icon-btn"
                onClick={() => toggleRightSidebarCollapsed(true)}
                title="收起右侧文件区"
                aria-label="收起右侧文件区"
              >
                <PanelRightCloseIcon size={15} />
              </button>
            </div>
          </div>

          {rightTab === "tree" ? (
            <div className="file-tree">
              {groupedFiles.length === 0 ? (
                <div className="empty-state compact">
                  暂无文件。上传申报指南、附件或草稿后会显示在这里。
                </div>
              ) : (
                groupedFiles.map(([category, categoryFiles]) => (
                  <div key={category} className="tree-node">
                    <div className="tree-row folder">
                      <FolderIcon size={15} />
                      <span className="fname">{categoryLabel[category]}</span>
                      <span className="fsize">{categoryFiles.length}</span>
                    </div>
                    <div className="tree-children open">
                      {categoryFiles.map((file) => (
                        <button
                          key={file.id}
                          type="button"
                          className={`tree-row${selectedFile?.id === file.id ? "active" : ""}`}
                          onClick={() => {
                            openFileDialog(file);
                          }}
                        >
                          <FileIcon size={14} />
                          <span className="fname">{file.name}</span>
                          <span className="fsize">{fileSize(file.size)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="file-preview">
              {selectedFile ? (
                <>
                  <div className="fp-meta">
                    <span>{categoryLabel[selectedFile.category]}</span>
                    <span>{fileSize(selectedFile.size)}</span>
                  </div>
                  <div className="fp-title">{selectedFile.name}</div>
                  <div className="fp-actions">
                    <button
                      type="button"
                      onClick={async () =>
                        downloadBlob(
                          await downloadProjectFile(projectId, selectedFile),
                          selectedFile.name,
                        )
                      }
                    >
                      <DownloadIcon size={14} />
                      下载
                    </button>
                    <button
                      type="button"
                      onClick={() => removeFile.mutate(selectedFile)}
                      disabled={removeFile.isPending}
                    >
                      <Trash2Icon size={14} />
                      删除
                    </button>
                  </div>
                  <div className="fp-content">
                    {fileContent.isLoading ? (
                      <div className="empty-state compact">正在读取文件</div>
                    ) : fileContent.isError ? (
                      <div className="empty-state compact">
                        该文件暂不支持在线预览，可直接下载查看。
                      </div>
                    ) : fileContent.data?.content ? (
                      <div className="msg-content file-markdown-view compact">
                        <MarkdownRenderer content={fileContent.data.content} />
                      </div>
                    ) : (
                      <div className="empty-state compact">
                        该文件暂不支持在线预览，可直接下载查看。
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="empty-state compact">请选择一个文件预览。</div>
              )}
            </div>
          )}
        </aside>
      </div>

      {directoryDialogOpen ? (
        <div
          className="modal-backdrop directory-modal-backdrop"
          role="presentation"
          onMouseDown={() => setDirectoryDialogOpen(false)}
        >
          <div
            className="directory-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="directory-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="file-modal-head">
              <div className="file-modal-title-wrap">
                <h2 id="directory-modal-title">打开项目目录</h2>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label="关闭"
                onClick={() => setDirectoryDialogOpen(false)}
              >
                <XIcon size={16} />
              </button>
            </div>

            <div className="directory-modal-body">
              <div className="directory-picker-field">
                <span>目录路径</span>
                <button
                  type="button"
                  className="directory-picker-button"
                  onClick={() => {
                    saveProjectDirectory.reset();
                    selectDirectory.reset();
                    setDirectoryNotice("");
                    selectDirectory.mutate();
                  }}
                  disabled={directoryPending}
                >
                  {selectDirectory.isPending ? (
                    <Loader2Icon size={15} className="spin" />
                  ) : (
                    <FolderOpenIcon size={15} />
                  )}
                  选择电脑目录
                </button>
                <strong>{directoryDraftPath || "未选择目录"}</strong>
              </div>
              <div className="directory-path-row">
                <span>当前</span>
                <strong>
                  {projectDirectory.data?.root_path ??
                    project.data?.root_path ??
                    "未设置"}
                </strong>
              </div>
            </div>

            <div className="export-modal-foot">
              <span
                className={
                  saveProjectDirectory.isError || selectDirectory.isError
                    ? "export-error"
                    : undefined
                }
              >
                {saveProjectDirectory.isError || selectDirectory.isError
                  ? directoryErrorMessage
                  : directoryNotice}
              </span>
              <div className="directory-modal-actions">
                <button
                  type="button"
                  onClick={() => saveDirectoryPath(null)}
                  disabled={directoryPending}
                >
                  {saveProjectDirectory.isPending &&
                  !directoryDraftPath.trim() ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <FolderIcon size={14} />
                  )}
                  使用默认目录
                </button>
                <button
                  type="button"
                  className="primary-btn"
                  onClick={() =>
                    saveDirectoryPath(directoryDraftPath.trim() || null)
                  }
                  disabled={directoryPending || !directoryDraftPath.trim()}
                >
                  {saveProjectDirectory.isPending &&
                  directoryDraftPath.trim() ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <SaveIcon size={14} />
                  )}
                  保存目录
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {fileDialogOpen && selectedFile ? (
        <div
          className="modal-backdrop file-modal-backdrop"
          role="presentation"
          onMouseDown={() => setFileDialogOpen(false)}
        >
          <div
            className="file-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="file-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="file-modal-head">
              <div className="file-modal-title-wrap">
                <div className="fp-meta">
                  <span>{categoryLabel[selectedFile.category]}</span>
                  <span>{fileSize(selectedFile.size)}</span>
                </div>
                <h2 id="file-modal-title">{selectedFile.name}</h2>
              </div>
              <div className="file-modal-actions">
                <button
                  type="button"
                  onClick={handleFileEditSave}
                  disabled={!canEditSelectedFile || saveFile.isPending}
                >
                  {fileEditing ? (
                    saveFile.isPending ? (
                      <Loader2Icon size={14} className="spin" />
                    ) : (
                      <SaveIcon size={14} />
                    )
                  ) : (
                    <PencilIcon size={14} />
                  )}
                  {fileEditing
                    ? saveFile.isPending
                      ? "保存中"
                      : "保存"
                    : "修改"}
                </button>
                <button
                  type="button"
                  className="file-delete-btn"
                  onClick={() => removeFile.mutate(selectedFile)}
                  disabled={removeFile.isPending || saveFile.isPending}
                >
                  {removeFile.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <Trash2Icon size={14} />
                  )}
                  {removeFile.isPending ? "删除中" : "删除"}
                </button>
                <button
                  type="button"
                  onClick={async () =>
                    downloadBlob(
                      await downloadProjectFile(projectId, selectedFile),
                      selectedFile.name,
                    )
                  }
                >
                  <DownloadIcon size={14} />
                  下载
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="关闭"
                  onClick={() => setFileDialogOpen(false)}
                >
                  <XIcon size={16} />
                </button>
              </div>
            </div>

            <div className="file-modal-body">
              {fileContent.isLoading ? (
                <div className="empty-state compact">正在读取文件</div>
              ) : fileContent.isError ? (
                <div className="empty-state compact">
                  该文件暂不支持在线预览，可直接下载查看。
                </div>
              ) : fileEditing ? (
                <textarea
                  className="file-modal-editor"
                  value={fileDraftContent}
                  onChange={(event) => setFileDraftContent(event.target.value)}
                />
              ) : displayedFileContent ? (
                <div className="msg-content file-markdown-view">
                  <MarkdownRenderer content={displayedFileContent} />
                </div>
              ) : (
                <div className="empty-state compact">文件为空</div>
              )}
            </div>
          </div>
        </div>
      ) : null}

      {exportDialogOpen ? (
        <div
          className="modal-backdrop export-modal-backdrop"
          role="presentation"
          onMouseDown={() => setExportDialogOpen(false)}
        >
          <div
            className="export-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="file-modal-head">
              <div className="file-modal-title-wrap">
                <div className="fp-meta">
                  <span>Word 导出</span>
                  <span>{selectedExportFiles.length} 个文件</span>
                </div>
                <h2 id="export-modal-title">导出项目文件</h2>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label="关闭"
                onClick={() => setExportDialogOpen(false)}
              >
                <XIcon size={16} />
              </button>
            </div>

            <div className="export-modal-body">
              <section className="export-section">
                <div className="export-section-head">
                  <div>
                    <h3>导出范围</h3>
                  </div>
                  <div className="export-range-actions">
                    <button
                      type="button"
                      onClick={() =>
                        setExportSelectedIds(
                          new Set(exportableFiles.map((file) => file.id)),
                        )
                      }
                    >
                      全选
                    </button>
                    <button
                      type="button"
                      onClick={() => setExportSelectedIds(new Set())}
                    >
                      清空
                    </button>
                  </div>
                </div>

                <div className="export-file-list">
                  {exportableGroups.length === 0 ? (
                    <div className="empty-state compact">
                      暂无可导出的 Markdown 或文本文件。
                    </div>
                  ) : (
                    exportableGroups.map(([category, categoryFiles]) => (
                      <div key={category} className="export-file-group">
                        <div className="export-file-group-title">
                          <FolderIcon size={14} />
                          <span>{categoryLabel[category]}</span>
                          <span>{categoryFiles.length}</span>
                        </div>
                        {categoryFiles.map((file) => (
                          <label key={file.id} className="export-file-row">
                            <input
                              type="checkbox"
                              checked={exportSelectedIds.has(file.id)}
                              onChange={() => toggleExportFile(file.id)}
                            />
                            <FileIcon size={14} />
                            <span className="fname">{file.name}</span>
                            <span className="fsize">{fileSize(file.size)}</span>
                          </label>
                        ))}
                      </div>
                    ))
                  )}
                </div>
              </section>

              <section className="export-section">
                <div className="export-section-head">
                  <div>
                    <h3>导出格式</h3>
                  </div>
                </div>
                <div className="export-mode-toggle">
                  <button
                    type="button"
                    className={exportMode === "merged" ? "active" : ""}
                    onClick={() => setExportMode("merged")}
                  >
                    合并导出
                  </button>
                  <button
                    type="button"
                    className={exportMode === "separate" ? "active" : ""}
                    onClick={() => setExportMode("separate")}
                  >
                    单独导出
                  </button>
                </div>

                <div className="export-image-choice">
                  <div className="export-image-choice-head">
                    <h3>是否插入图片</h3>
                    <ImageIcon size={18} aria-hidden="true" />
                  </div>
                  <div
                    className="export-mode-toggle export-image-toggle"
                    role="group"
                    aria-label="是否插入图片"
                  >
                    <button
                      type="button"
                      className={!includeImages ? "active" : ""}
                      disabled={exportFiles.isPending}
                      onClick={() => setIncludeImages(false)}
                    >
                      不插入图片
                    </button>
                    <button
                      type="button"
                      className={includeImages ? "active" : ""}
                      disabled={exportFiles.isPending}
                      onClick={() => setIncludeImages(true)}
                    >
                      智能匹配并插入
                    </button>
                  </div>
                </div>
              </section>
            </div>

            <div className="export-modal-foot">
              <span
                className={exportFiles.isError ? "export-error" : undefined}
              >
                {exportFiles.isError
                  ? exportErrorMessage
                  : selectedExportFiles.length > 0
                    ? `已选择 ${selectedExportFiles.length} 个文件`
                    : "请选择至少一个文件"}
              </span>
              <button
                type="button"
                className="primary-btn"
                disabled={
                  selectedExportFiles.length === 0 || exportFiles.isPending
                }
                onClick={() => {
                  exportFiles.reset();
                  exportFiles.mutate({
                    items: selectedExportFiles,
                    mode: exportMode,
                    includeImages,
                  });
                }}
              >
                {exportFiles.isPending ? (
                  <Loader2Icon size={14} className="spin" />
                ) : (
                  <DownloadIcon size={14} />
                )}
                {exportFiles.isPending
                  ? includeImages
                    ? "智能匹配并导出中"
                    : "导出中"
                  : includeImages
                    ? "智能插图并导出"
                    : "导出 Word"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
