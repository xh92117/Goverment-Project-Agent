"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  FolderIcon,
  MoonIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PencilIcon,
  PinIcon,
  PlusIcon,
  Settings2Icon,
  SunIcon,
  Trash2Icon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useMemo, useState } from "react";

import { WorkspaceAccount } from "@/features/auth/workspace-account";
import { createThread, deleteThread, patchThread, searchThreads } from "@/features/chat/api";
import type { ThreadRecord } from "@/features/chat/api";
import { UNTITLED_DIRECT_THREAD_TITLE, UNTITLED_PROJECT_THREAD_TITLE } from "@/features/chat/thread-title";
import { createProject, deleteProject, listProjects, patchProject } from "@/features/projects/api";
import type { ProjectRecord } from "@/features/projects/api";
import { createId } from "@/shared/lib/ids";
import { useThemeMode } from "@/shared/theme/use-theme";

function metadataText(record: { metadata?: Record<string, unknown> }, key: string) {
  const value = record.metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function metadataBoolean(record: { metadata?: Record<string, unknown> }, key: string) {
  return record.metadata?.[key] === true;
}

function projectIdFromPath(pathname: string) {
  const match = /\/workspace\/projects\/([^/]+)/.exec(pathname);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function threadIdFromPath(pathname: string) {
  const match = /\/threads\/([^/]+)/.exec(pathname);
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function threadTitle(thread: ThreadRecord) {
  return (
    metadataText(thread, "title") ??
    metadataText(thread, "name") ??
    metadataText(thread, "topic") ??
    `对话 ${thread.thread_id.slice(0, 8)}`
  );
}

function projectTitle(project: ProjectRecord) {
  return project.name || `项目 ${project.project_id.slice(0, 8)}`;
}

function mergeMetadata<T extends { metadata?: Record<string, unknown> }>(
  record: T,
  patch: Record<string, unknown>,
) {
  return { ...(record.metadata ?? {}), ...patch };
}

function sortedThreads(items: ThreadRecord[]) {
  return [...items].sort((left, right) => {
    const leftPinned = metadataBoolean(left, "pinned") ? 1 : 0;
    const rightPinned = metadataBoolean(right, "pinned") ? 1 : 0;
    if (leftPinned !== rightPinned) return rightPinned - leftPinned;
    return String(right.updated_at ?? "").localeCompare(String(left.updated_at ?? ""));
  });
}

function projectHref(projectId: string) {
  return `/workspace/projects/${encodeURIComponent(projectId)}`;
}

function threadHref(projectId: string, threadId: string) {
  return `${projectHref(projectId)}/threads/${encodeURIComponent(threadId)}`;
}

const SIDEBAR_WIDTH_STORAGE_KEY = "workspace-sidebar-left-width";
const SIDEBAR_DEFAULT_WIDTH = 264;
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 420;

function clampSidebarWidth(width: number) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)));
}

function getStoredSidebarWidth() {
  if (typeof window === "undefined") return null;
  try {
    const value = Number(window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY));
    return Number.isFinite(value) ? clampSidebarWidth(value) : null;
  } catch {
    return null;
  }
}

function ThreadRow({
  thread,
  href,
  active,
  onRename,
  onDelete,
  onTogglePin,
}: {
  thread: ThreadRecord;
  href: string;
  active: boolean;
  onRename: (thread: ThreadRecord) => void;
  onDelete: (thread: ThreadRecord) => void;
  onTogglePin: (thread: ThreadRecord) => void;
}) {
  const pinned = metadataBoolean(thread, "pinned");
  return (
    <div className={`thread-item${active ? " active" : ""}${pinned ? " pinned-thread" : ""}`}>
      <Link href={href} className="thread-link">
        <span className="ti-dot" />
        <span className="ti-name">{threadTitle(thread)}</span>
      </Link>
      <div className="row-actions">
        <button type="button" title={pinned ? "取消置顶对话" : "置顶对话"} onClick={() => onTogglePin(thread)}>
          <PinIcon className={`pin sm${pinned ? "" : " ghost"}`} />
        </button>
        <button type="button" title="重命名对话" onClick={() => onRename(thread)}>
          <PencilIcon />
        </button>
        <button type="button" title="删除对话" className="danger" onClick={() => onDelete(thread)}>
          <Trash2Icon />
        </button>
      </div>
    </div>
  );
}

function ProjectGroup({
  project,
  threads,
  expanded,
  activeProjectId,
  activeThreadId,
  pinned,
  onToggle,
  onRenameProject,
  onDeleteProject,
  onToggleProjectPin,
  onRenameThread,
  onDeleteThread,
  onToggleThreadPin,
  onCreateThread,
  creatingThread,
}: {
  project: ProjectRecord;
  threads: ThreadRecord[];
  expanded: boolean;
  activeProjectId: string | null;
  activeThreadId: string | null;
  pinned: boolean;
  onToggle: () => void;
  onRenameProject: (project: ProjectRecord) => void;
  onDeleteProject: (project: ProjectRecord) => void;
  onToggleProjectPin: (project: ProjectRecord) => void;
  onRenameThread: (thread: ThreadRecord) => void;
  onDeleteThread: (thread: ThreadRecord) => void;
  onToggleThreadPin: (thread: ThreadRecord) => void;
  onCreateThread: (project: ProjectRecord) => void;
  creatingThread?: boolean;
}) {
  const activeProject = activeProjectId === project.project_id;
  const projectThreads = sortedThreads(threads).slice(0, 8);

  return (
    <div className="proj-group">
      <div className={`proj-item${activeProject ? " active" : ""}${expanded ? " expanded" : ""}${pinned ? " pinned" : ""}`}>
        <button type="button" className="proj-toggle" onClick={onToggle} aria-label="展开项目对话">
          {expanded ? <ChevronDownIcon className="chev" /> : <ChevronRightIcon className="chev" />}
        </button>
        <Link href={projectHref(project.project_id)} className="proj-link">
          <FolderIcon className="pi-icon" />
          <span className="pi-name">{projectTitle(project)}</span>
        </Link>
        <div className="row-actions project-actions">
          <button type="button" title={pinned ? "取消置顶项目" : "置顶项目"} onClick={() => onToggleProjectPin(project)}>
            <PinIcon className={`pin${pinned ? "" : " ghost"}`} />
          </button>
          <button type="button" title="重命名项目" onClick={() => onRenameProject(project)}>
            <PencilIcon />
          </button>
          <button type="button" title="删除项目" className="danger" onClick={() => onDeleteProject(project)}>
            <Trash2Icon />
          </button>
          {expanded ? (
            <button
              type="button"
              title="新建对话"
              onClick={() => onCreateThread(project)}
              disabled={creatingThread}
            >
              <PlusIcon />
            </button>
          ) : null}
        </div>
      </div>

      <div className={`thread-list${expanded ? " open" : ""}`}>
        {projectThreads.length === 0 ? (
          <div className="thread-empty">暂无项目对话</div>
        ) : (
          projectThreads.map((thread) => {
            const active = activeThreadId === thread.thread_id;
            return (
              <ThreadRow
                key={thread.thread_id}
                thread={thread}
                href={threadHref(project.project_id, thread.thread_id)}
                active={active}
                onRename={onRenameThread}
                onDelete={onDeleteThread}
                onTogglePin={onToggleThreadPin}
              />
            );
          })
        )}
      </div>
    </div>
  );
}

export function WorkspaceShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { theme, toggleTheme } = useThemeMode();
  const [collapsed, setCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [resizingSidebar, setResizingSidebar] = useState(false);
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());
  const [pinnedProjectsOpen, setPinnedProjectsOpen] = useState(true);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatMode, setNewChatMode] = useState<"project" | "direct">("project");
  const [newProjectName, setNewProjectName] = useState("");

  const activeProjectId = projectIdFromPath(pathname);
  const activeThreadId = threadIdFromPath(pathname) ?? searchParams.get("thread");

  useEffect(() => {
    const storedWidth = getStoredSidebarWidth();
    if (storedWidth) setSidebarWidth(storedWidth);
  }, []);

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
    staleTime: 20_000,
  });

  const threads = useQuery({
    queryKey: ["threads", "sidebar"],
    queryFn: () => searchThreads(120),
    staleTime: 15_000,
  });

  useEffect(() => {
    if (!projects.data?.length) return;
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (activeProjectId) next.add(activeProjectId);
      else next.add(projects.data[0]?.project_id ?? "");
      next.delete("");
      return next;
    });
  }, [activeProjectId, projects.data]);

  const threadsByProject = useMemo(() => {
    const map = new Map<string, ThreadRecord[]>();
    for (const thread of threads.data ?? []) {
      const projectId = metadataText(thread, "project_id");
      if (!projectId) continue;
      map.set(projectId, [...(map.get(projectId) ?? []), thread]);
    }
    return map;
  }, [threads.data]);

  const [pinnedProjects, historyProjects] = useMemo(() => {
    const allProjects = projects.data ?? [];
    const pinned = allProjects.filter((project) => metadataBoolean(project, "pinned"));
    return [pinned, allProjects.filter((project) => !pinned.includes(project))];
  }, [projects.data]);

  const looseThreads = useMemo(
    () => (threads.data ?? []).filter((thread) => !metadataText(thread, "project_id")).slice(0, 8),
    [threads.data],
  );

  const createChat = useMutation({
    mutationFn: async () => {
      const threadId = createId();
      if (newChatMode === "project") {
        const projectName = newProjectName.trim() || "未命名申报项目";
        const project = await createProject({
          name: projectName,
          metadata: {
            workspace_layout: "codex-design",
            created_from: "new-chat-modal",
          },
        });
        await createThread(threadId, {
          project_id: project.project_id,
          project_name: project.name,
          title: UNTITLED_PROJECT_THREAD_TITLE,
          source: "workspace-sidebar",
          project_type: "government-project-declaration",
        });
        return {
          href: `${projectHref(project.project_id)}/threads/${encodeURIComponent(threadId)}`,
        };
      }
      await createThread(threadId, {
        title: UNTITLED_DIRECT_THREAD_TITLE,
        source: "workspace-sidebar",
        project_type: "government-project-declaration",
      });
      return {
        href: `/workspace/chat?thread=${encodeURIComponent(threadId)}`,
      };
    },
    onSuccess: async (result) => {
      setNewChatOpen(false);
      setNewProjectName("");
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(result.href);
    },
  });

  const createProjectConversation = useMutation({
    mutationFn: async (project: ProjectRecord) => {
      const threadId = createId();
      await createThread(threadId, {
        project_id: project.project_id,
        project_name: project.name,
        title: UNTITLED_PROJECT_THREAD_TITLE,
        source: "workspace-project-history",
        project_type: "government-project-declaration",
      });
      return {
        projectId: project.project_id,
        threadId,
      };
    },
    onSuccess: ({ projectId, threadId }) => {
      setExpandedProjects((current) => {
        const next = new Set(current);
        next.add(projectId);
        return next;
      });
      router.push(threadHref(projectId, threadId));
      void queryClient.invalidateQueries({ queryKey: ["threads"] });
      void queryClient.invalidateQueries({ queryKey: ["project-threads", projectId] });
    },
  });

  const renameProject = useMutation({
    mutationFn: ({ project, name }: { project: ProjectRecord; name: string }) =>
      patchProject(project.project_id, { name }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  const toggleProjectPin = useMutation({
    mutationFn: (project: ProjectRecord) =>
      patchProject(project.project_id, {
        metadata: mergeMetadata(project, { pinned: !metadataBoolean(project, "pinned") }),
      }),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  const removeProject = useMutation({
    mutationFn: (project: ProjectRecord) => deleteProject(project.project_id),
    onSuccess: async (_, project) => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      if (activeProjectId === project.project_id) router.push("/workspace/projects");
    },
  });

  const renameThread = useMutation({
    mutationFn: ({ thread, title }: { thread: ThreadRecord; title: string }) =>
      patchThread(thread.thread_id, mergeMetadata(thread, { title })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      await queryClient.invalidateQueries({ queryKey: ["project-threads"] });
    },
  });

  const toggleThreadPin = useMutation({
    mutationFn: (thread: ThreadRecord) =>
      patchThread(thread.thread_id, mergeMetadata(thread, { pinned: !metadataBoolean(thread, "pinned") })),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      await queryClient.invalidateQueries({ queryKey: ["project-threads"] });
    },
  });

  const removeThread = useMutation({
    mutationFn: (thread: ThreadRecord) => deleteThread(thread.thread_id),
    onSuccess: async (_, thread) => {
      await queryClient.invalidateQueries({ queryKey: ["threads"] });
      await queryClient.invalidateQueries({ queryKey: ["project-threads"] });
      if (activeThreadId === thread.thread_id) {
        const projectId = metadataText(thread, "project_id");
        router.push(projectId ? projectHref(projectId) : "/workspace/chat");
      }
    },
  });

  function requestProjectRename(project: ProjectRecord) {
    const next = window.prompt("重命名项目", projectTitle(project))?.trim();
    if (next && next !== projectTitle(project)) renameProject.mutate({ project, name: next });
  }

  function requestProjectDelete(project: ProjectRecord) {
    if (window.confirm(`确定删除项目“${projectTitle(project)}”？项目文件和关联数据可能会被后端同步删除。`)) {
      removeProject.mutate(project);
    }
  }

  function requestThreadRename(thread: ThreadRecord) {
    const next = window.prompt("重命名对话", threadTitle(thread))?.trim();
    if (next && next !== threadTitle(thread)) renameThread.mutate({ thread, title: next });
  }

  function requestThreadDelete(thread: ThreadRecord) {
    if (window.confirm(`确定删除对话“${threadTitle(thread)}”？`)) removeThread.mutate(thread);
  }

  function toggleProject(projectId: string) {
    setExpandedProjects((current) => {
      const next = new Set(current);
      if (next.has(projectId)) next.delete(projectId);
      else next.add(projectId);
      return next;
    });
  }

  function handleSidebarResizePointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
    event.preventDefault();
    if (collapsed) setCollapsed(false);

    const startX = event.clientX;
    const startWidth = sidebarWidth;
    let nextWidth = startWidth;

    setResizingSidebar(true);
    document.documentElement.classList.add("sidebar-resizing");

    const handlePointerMove = (moveEvent: PointerEvent) => {
      nextWidth = clampSidebarWidth(startWidth + moveEvent.clientX - startX);
      setSidebarWidth(nextWidth);
    };

    const finishResize = () => {
      setResizingSidebar(false);
      document.documentElement.classList.remove("sidebar-resizing");
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", finishResize);
      window.removeEventListener("pointercancel", finishResize);
      try {
        window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
      } catch {
        // Ignore storage failures; resizing should still work for the current session.
      }
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", finishResize);
    window.addEventListener("pointercancel", finishResize);
  }

  const appStyle = {
    "--left-w": `${sidebarWidth}px`,
  } as CSSProperties & { "--left-w": string };

  return (
    <div
      className={`app${collapsed ? " collapse-left" : ""}${resizingSidebar ? " resizing-left" : ""}`}
      id="app"
      style={appStyle}
    >
      {collapsed && (
        <button
          type="button"
          className="corner-btn left"
          title="展开左侧栏"
          aria-label="展开左侧栏"
          onClick={() => setCollapsed(false)}
        >
          <PanelLeftOpenIcon />
        </button>
      )}

      <aside className="sidebar-left">
        <div className="sl-head sl-head-minimal">
          <button type="button" className="icon-btn" title="收起侧栏" onClick={() => setCollapsed(true)}>
            <PanelLeftCloseIcon />
          </button>
        </div>

        <button type="button" className="new-chat" onClick={() => setNewChatOpen(true)} disabled={createChat.isPending}>
          <PlusIcon />
          {createChat.isPending ? "创建中" : "新对话"}
        </button>

        <div className="nav-sections">
          <div className="list-section">
            <button
              type="button"
              className="list-section-title list-section-toggle"
              onClick={() => {
                if (pinnedProjects.length) setPinnedProjectsOpen((current) => !current);
              }}
              disabled={!pinnedProjects.length}
              aria-expanded={pinnedProjectsOpen}
            >
              <span>置顶项目</span>
              <span className="list-section-meta">
                {pinnedProjects.length ? (
                  pinnedProjectsOpen ? (
                    <ChevronDownIcon />
                  ) : (
                    <ChevronRightIcon />
                  )
                ) : null}
                <span className="count">{pinnedProjects.length}</span>
              </span>
            </button>
            {pinnedProjects.length > 0 && pinnedProjectsOpen ? (
              pinnedProjects.map((project) => (
                <ProjectGroup
                  key={project.project_id}
                  project={project}
                  threads={threadsByProject.get(project.project_id) ?? []}
                  expanded={expandedProjects.has(project.project_id)}
                  activeProjectId={activeProjectId}
                  activeThreadId={activeThreadId}
                  pinned
                  onToggle={() => toggleProject(project.project_id)}
                  onRenameProject={requestProjectRename}
                  onDeleteProject={requestProjectDelete}
                  onToggleProjectPin={(item) => toggleProjectPin.mutate(item)}
                  onRenameThread={requestThreadRename}
                  onDeleteThread={requestThreadDelete}
                  onToggleThreadPin={(item) => toggleThreadPin.mutate(item)}
                  onCreateThread={(item) => createProjectConversation.mutate(item)}
                  creatingThread={createProjectConversation.isPending}
                />
              ))
            ) : null}
          </div>

          <div className="list-section">
            <div className="list-section-title">
              <span>项目</span>
              <span className="count">{historyProjects.length}</span>
            </div>
            {projects.isLoading ? (
              <div className="sidebar-muted">正在加载项目</div>
            ) : historyProjects.length === 0 ? (
              null
            ) : (
              historyProjects.map((project) => (
                <ProjectGroup
                  key={project.project_id}
                  project={project}
                  threads={threadsByProject.get(project.project_id) ?? []}
                  expanded={expandedProjects.has(project.project_id)}
                  activeProjectId={activeProjectId}
                  activeThreadId={activeThreadId}
                  pinned={false}
                  onToggle={() => toggleProject(project.project_id)}
                  onRenameProject={requestProjectRename}
                  onDeleteProject={requestProjectDelete}
                  onToggleProjectPin={(item) => toggleProjectPin.mutate(item)}
                  onRenameThread={requestThreadRename}
                  onDeleteThread={requestThreadDelete}
                  onToggleThreadPin={(item) => toggleThreadPin.mutate(item)}
                  onCreateThread={(item) => createProjectConversation.mutate(item)}
                  creatingThread={createProjectConversation.isPending}
                />
              ))
            )}
          </div>

          <div className="list-section">
            <div className="list-section-title">
              <span>独立对话</span>
              <span className="count">{looseThreads.length}</span>
            </div>
            {looseThreads.length > 0 ? (
              <div className="thread-list open standalone">
                {sortedThreads(looseThreads).map((thread) => (
                  <ThreadRow
                    key={thread.thread_id}
                    thread={thread}
                    href={`/workspace/chat?thread=${encodeURIComponent(thread.thread_id)}`}
                    active={activeThreadId === thread.thread_id}
                    onRename={requestThreadRename}
                    onDelete={requestThreadDelete}
                    onTogglePin={(item) => toggleThreadPin.mutate(item)}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <div className="sl-foot">
          <WorkspaceAccount />
          <Link className={`foot-btn${pathname.startsWith("/workspace/knowledge") ? " active" : ""}`} href="/workspace/knowledge">
            <BookOpenIcon />
            知识库
          </Link>
          <Link className={`foot-btn${pathname.startsWith("/workspace/settings") ? " active" : ""}`} href="/workspace/settings">
            <Settings2Icon />
            设置
          </Link>
          <button type="button" className="theme-toggle" onClick={toggleTheme}>
            <span className="t-label">
              {theme === "dark" ? <MoonIcon /> : <SunIcon />}
              <span>{theme === "dark" ? "深色主题" : "浅色主题"}</span>
            </span>
            <span className={`switch${theme === "dark" ? " on" : ""}`} />
          </button>
        </div>

        <button
          type="button"
          className="sidebar-resize-handle"
          aria-label="调整左侧栏宽度"
          title="拖动调整左侧栏宽度"
          onDoubleClick={() => setSidebarWidth(SIDEBAR_DEFAULT_WIDTH)}
          onPointerDown={handleSidebarResizePointerDown}
        />
      </aside>

      <div className="workspace-slot">{children}</div>

      {newChatOpen ? (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setNewChatOpen(false)}>
          <div className="new-chat-modal" role="dialog" aria-modal="true" aria-labelledby="new-chat-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h2 id="new-chat-title">新对话</h2>
                <p>选择创建新的申报项目，或直接开启独立对话。</p>
              </div>
              <button type="button" className="icon-btn" aria-label="关闭" onClick={() => setNewChatOpen(false)}>
                ×
              </button>
            </div>

            <div className="mode-grid">
              <button
                type="button"
                className={`mode-card${newChatMode === "project" ? " active" : ""}`}
                onClick={() => setNewChatMode("project")}
              >
                <FolderIcon />
                <span>新建项目</span>
                <small>创建项目空间、材料目录和项目会话</small>
              </button>
              <button
                type="button"
                className={`mode-card${newChatMode === "direct" ? " active" : ""}`}
                onClick={() => setNewChatMode("direct")}
              >
                <BookOpenIcon />
                <span>直接对话</span>
                <small>不绑定项目，创建一个独立申报咨询会话</small>
              </button>
            </div>

            {newChatMode === "project" ? (
              <label className="modal-field">
                <span>项目名称</span>
                <input
                  value={newProjectName}
                  placeholder="例如：2026年度重点研发计划申报"
                  onChange={(event) => setNewProjectName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") createChat.mutate();
                  }}
                />
              </label>
            ) : null}

            <div className="modal-actions">
              <button type="button" className="ghost-btn" onClick={() => setNewChatOpen(false)}>
                取消
              </button>
              <button type="button" className="primary-btn" onClick={() => createChat.mutate()} disabled={createChat.isPending}>
                <PlusIcon size={15} />
                {createChat.isPending ? "创建中" : newChatMode === "project" ? "创建项目并开始" : "开始独立对话"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
