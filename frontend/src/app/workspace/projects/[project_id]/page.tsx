import { ProjectWorkspacePage } from "@/features/projects/project-workspace-page";

export default async function Page({
  params,
}: Readonly<{ params: Promise<{ project_id: string }> }>) {
  const { project_id: projectId } = await params;
  return <ProjectWorkspacePage projectId={projectId} />;
}
