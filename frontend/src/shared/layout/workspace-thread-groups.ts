type MetadataRecord = {
  metadata?: Record<string, unknown>;
};

type ProjectIdentity = {
  project_id: string;
};

function threadProjectId(thread: MetadataRecord): string | null {
  const value = thread.metadata?.project_id;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function threadsWithoutAvailableProject<T extends MetadataRecord>(
  threads: readonly T[],
  projects: readonly ProjectIdentity[],
): T[] {
  const availableProjectIds = new Set(
    projects.map((project) => project.project_id),
  );
  return threads.filter((thread) => {
    const projectId = threadProjectId(thread);
    return projectId === null || !availableProjectIds.has(projectId);
  });
}
