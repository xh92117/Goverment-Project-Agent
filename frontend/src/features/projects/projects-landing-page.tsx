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
import { useState } from "react";

import { createProject, listProjects } from "@/features/projects/api";
import { formatDateTime } from "@/shared/lib/format";

const quickCards = [
  {
    title: "新建申报项目",
    desc: "创建项目空间、材料目录和对话上下文",
    icon: FolderPlusIcon,
  },
  {
    title: "整理知识库",
    desc: "上传政策文件，一键构建检索索引",
    icon: BookOpenIcon,
    href: "/workspace/knowledge",
  },
  {
    title: "配置智能体",
    desc: "管理模型供应商、技能与 MCP",
    icon: Settings2Icon,
    href: "/workspace/settings",
  },
  {
    title: "草稿工作台",
    desc: "查看和维护申报书章节草稿",
    icon: FileTextIcon,
    href: "/workspace/drafts",
  },
];

export function ProjectsLandingPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });

  const create = useMutation({
    mutationFn: () =>
      createProject({
        name: name.trim() || "未命名申报项目",
        metadata: {
          workspace_layout: "codex-design",
          created_from: "web-project-entry",
        },
      }),
    onSuccess: async (project) => {
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      router.push(`/workspace/projects/${encodeURIComponent(project.project_id)}`);
    },
  });

  return (
    <main className="codex-main single">
      <header className="main-head">
        <div>
          <div className="mh-title">开始新的项目申报</div>
          <div className="mh-breadcrumb">描述需求、创建空间，然后进入协作工作台</div>
        </div>
      </header>

      <div className="welcome-view">
        <div className="welcome-emblem">策</div>
        <h1>智策政府科研项目申报助手</h1>
        <p>以项目为中心组织政策、材料、草稿和智能体对话，适合持续推进申报书撰写与材料校验。</p>

        <form
          className="project-create-box"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <input
            value={name}
            placeholder="输入项目名称，例如：2026年度重点研发计划申报"
            onChange={(event) => setName(event.target.value)}
          />
          <button type="submit" disabled={create.isPending}>
            <PlusIcon size={16} />
            {create.isPending ? "创建中" : "创建项目"}
          </button>
        </form>

        <div className="quick-grid">
          {quickCards.map((card) => {
            const Icon = card.icon;
            const content = (
              <>
                <Icon className="qc-icon" size={22} />
                <div className="qc-title">{card.title}</div>
                <div className="qc-desc">{card.desc}</div>
              </>
            );
            return card.href ? (
              <Link key={card.title} className="quick-card" href={card.href}>
                {content}
              </Link>
            ) : (
              <button key={card.title} type="button" className="quick-card" onClick={() => create.mutate()}>
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
