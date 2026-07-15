import { Suspense } from "react";

import { WorkspaceShell } from "@/shared/layout/workspace-shell";

export default function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <Suspense fallback={<div className="workspace-loading">正在打开工作台...</div>}>
      <WorkspaceShell>{children}</WorkspaceShell>
    </Suspense>
  );
}
