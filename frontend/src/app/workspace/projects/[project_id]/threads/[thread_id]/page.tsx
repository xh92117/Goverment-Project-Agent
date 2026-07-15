import { ProjectWorkspacePage } from "@/features/projects/project-workspace-page";

export default async function Page({
  params,
}: Readonly<{ params: Promise<{ project_id: string; thread_id: string }> }>) {
  const { project_id: projectId, thread_id: threadId } = await params;
  return <ProjectWorkspacePage projectId={projectId} initialThreadId={threadId} />;
}
