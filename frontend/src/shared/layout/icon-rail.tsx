"use client";

import Link from "next/link";

export function IconRail() {
  return (
    <aside className="icon-rail" aria-label="兼容导航">
      <Link href="/workspace/projects" className="icon-rail-seal" aria-label="首页">
        策
      </Link>
    </aside>
  );
}
