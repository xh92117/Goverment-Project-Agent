"use client";

import {
  BookOpenIcon,
  FolderKanbanIcon,
  MoonIcon,
  Settings2Icon,
  SunIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useThemeMode } from "@/shared/theme/use-theme";

const nav = [
  { href: "/workspace/projects", label: "项目", icon: FolderKanbanIcon },
  { href: "/workspace/knowledge", label: "知识库", icon: BookOpenIcon },
  { href: "/workspace/settings", label: "设置", icon: Settings2Icon },
];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useThemeMode();

  useEffect(() => {
    for (const item of nav) {
      if (item.href !== pathname) router.prefetch(item.href);
    }
  }, [pathname, router]);

  return (
    <header className="topbar">
      <Link className="brand" href="/workspace/projects">
        <div className="brand-seal">策</div>
        <div className="brand-meta">
          <div className="brand-name">智策 · GovDecl</div>
          <div className="brand-tag">AI 申报助手</div>
        </div>
      </Link>

      <nav className="main-nav" aria-label="主导航">
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              className={`main-nav-item${active ? " active" : ""}`}
              href={item.href}
              prefetch
              onFocus={() => router.prefetch(item.href)}
              onPointerEnter={() => router.prefetch(item.href)}
            >
              <Icon size={15} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="topbar-right">
        <button
          type="button"
          className="theme-toggle"
          aria-label="切换主题"
          title="切换主题"
          onClick={toggleTheme}
        >
          {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
        </button>
      </div>
    </header>
  );
}

