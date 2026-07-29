"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRightIcon,
  BookOpenIcon,
  FileTextIcon,
  FolderPlusIcon,
  PlusIcon,
  Settings2Icon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { createProject, listProjects } from "@/features/projects/api";
import {
  isNewProjectDirectoryReady,
  newProjectRootPath,
} from "@/features/projects/new-project-directory";
import type { NewProjectDirectoryMode } from "@/features/projects/new-project-directory";
import { NewProjectDirectoryField } from "@/features/projects/new-project-directory-field";
import { formatDateTime } from "@/shared/lib/format";

const quickCards = [
  {
    title: "新建申报项目",
    icon: FolderPlusIcon,
  },
  {
    title: "整理知识库",
    icon: BookOpenIcon,
    href: "/workspace/knowledge",
  },
  {
    title: "配置智能体",
    icon: Settings2Icon,
    href: "/workspace/settings",
  },
  {
    title: "草稿工作台",
    icon: FileTextIcon,
    href: "/workspace/drafts",
  },
];

export function ProjectsLandingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const nameInputRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [directoryMode, setDirectoryMode] =
    useState<NewProjectDirectoryMode>(null);
  const [rootPath, setRootPath] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const directoryReady = isNewProjectDirectoryReady(directoryMode, rootPath);

  const create = useMutation({
    mutationFn: () => {
      if (!directoryReady) {
        throw new Error("请先选择项目工作路径。");
      }
      return createProject({
        name: name.trim() || "未命名申报项目",
        root_path: newProjectRootPath(directoryMode, rootPath),
        metadata: {
          workspace_layout: "codex-design",
          created_from: "web-project-entry",
        },
      });
    },
    onSuccess: async (project) => {
      setName("");
      setDirectoryMode(null);
      setRootPath("");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/workspace/projects/${encodeURIComponent(project.project_id)}`);
    },
  });

  return (
    <main className="codex-main single projects-landing-main">
      <header className="main-head">
        <div>
          <div className="mh-title">开始新的项目申报</div>
        </div>
      </header>

      <div className="welcome-view">
        <div className="welcome-emblem">策</div>
        <h1>智策政府科研项目申报助手</h1>
        <p>项目集中管理材料、知识库、对话和草稿。</p>

        <form
          className="project-create-panel"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <div className="project-create-box">
            <input
              ref={nameInputRef}
              value={name}
              placeholder="输入项目名称，例如：2026年度重点研发计划申报"
              onChange={(event) => setName(event.target.value)}
            />
            <button
              type="submit"
              disabled={create.isPending || !directoryReady}
            >
              <PlusIcon size={16} />
              {create.isPending ? "创建中" : "创建项目"}
            </button>
          </div>
          <NewProjectDirectoryField
            mode={directoryMode}
            rootPath={rootPath}
            disabled={create.isPending}
            onChange={(mode, selectedRootPath) => {
              setDirectoryMode(mode);
              setRootPath(selectedRootPath);
            }}
          />
          {create.isError ? (
            <p className="modal-error">
              {create.error instanceof Error
                ? create.error.message
                : "创建失败，请稍后重试。"}
            </p>
          ) : null}
        </form>

        <div className="quick-grid">
          {quickCards.map((card) => {
            const Icon = card.icon;
            const content = (
              <>
                <Icon className="qc-icon" size={22} />
                <div className="qc-title">{card.title}</div>
              </>
            );
            return card.href ? (
              <Link key={card.title} className="quick-card" href={card.href}>
                {content}
              </Link>
            ) : (
              <button
                key={card.title}
                type="button"
                className="quick-card"
                onClick={() => {
                  nameInputRef.current?.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                  nameInputRef.current?.focus();
                }}
              >
                {content}
              </button>
            );
          })}
        </div>

        <section className="recent-projects">
          <div className="section-heading">
            <h2>最近项目</h2>
            <span>{projects.data?.length ?? 0} 个项目</span>
          </div>
          {projects.isLoading ? (
            <div className="empty-state compact">正在加载项目</div>
          ) : projects.data?.length ? (
            <div className="project-card-grid">
              {projects.data.slice(0, 6).map((project) => (
                <Link
                  key={project.project_id}
                  href={`/workspace/projects/${encodeURIComponent(project.project_id)}`}
                  className="project-card"
                >
                  <div>
                    <h3>{project.name}</h3>
                    <p>{project.status || "进行中"} · {formatDateTime(project.updated_at)}</p>
                  </div>
                  <ArrowRightIcon size={16} />
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-state compact">暂无项目。创建后会自动进入项目工作台。</div>
          )}
        </section>
      </div>
    </main>
  );
}
