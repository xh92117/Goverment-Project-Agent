"use client";

import { DatabaseIcon, MoonIcon, ShieldCheckIcon, SparklesIcon, SunIcon, UsersIcon } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { useThemeMode } from "@/shared/theme/use-theme";

export function AuthPageShell({
  eyebrow,
  title,
  description,
  children,
  admin = false,
}: Readonly<{
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  admin?: boolean;
}>) {
  const { theme, toggleTheme } = useThemeMode();

  return (
    <main className="auth-page">
      <div className="auth-orb auth-orb-one" aria-hidden="true" />
      <div className="auth-orb auth-orb-two" aria-hidden="true" />

      <header className="auth-topbar">
        <Link className="auth-brand" href="/workspace/projects" aria-label="智策科研项目申报助手">
          <span className="auth-brand-mark">策</span>
          <span>
            <strong>智策</strong>
            <small>科研项目申报助手</small>
          </span>
        </Link>
        <button className="auth-theme-button" type="button" onClick={toggleTheme} aria-label="切换明暗主题">
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>
      </header>

      <div className="auth-layout">
        <section className="auth-story" aria-label="平台能力">
          <div className="auth-story-kicker">
            <SparklesIcon aria-hidden="true" />
            AI 驱动的申报协作空间
          </div>
          <h1>{admin ? "从安全的管理员账号开始" : "让每一次申报，更有依据"}</h1>
          <p>
            {admin
              ? "创建首位管理员后，系统将按登录账号隔离项目文件、对话、缓存、日志与个人知识内容。"
              : "政策检索、材料组织、知识沉淀与申报写作在同一个工作台内有序协同。"}
          </p>
          <div className="auth-capabilities">
            <div>
              <span><UsersIcon aria-hidden="true" /></span>
              <strong>账号空间隔离</strong>
              <small>用户数据按账号边界独立保存</small>
            </div>
            <div>
              <span><DatabaseIcon aria-hidden="true" /></span>
              <strong>双层知识体系</strong>
              <small>公共知识与个人知识彼此独立</small>
            </div>
            <div>
              <span><ShieldCheckIcon aria-hidden="true" /></span>
              <strong>会话安全保护</strong>
              <small>HttpOnly Cookie 与请求校验</small>
            </div>
          </div>
        </section>

        <section className="auth-panel" aria-label={title}>
          <div className="auth-panel-heading">
            <span>{eyebrow}</span>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
          {children}
        </section>
      </div>

      <footer className="auth-footer">
        <span>© 2026 智策 · GovDecl</span>
        <span>数据边界清晰 · 操作全程可追溯</span>
      </footer>
    </main>
  );
}
