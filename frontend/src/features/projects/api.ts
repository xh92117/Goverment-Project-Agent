import { apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface ProjectRecord {
  project_id: string;
  name: string;
  type: string;
  status: string;
  root_path: string;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, unknown>;
}

export interface ProjectFileNode {
  id: string;
  name: string;
  path: string;
  read_path: string;
  kind: "file";
  category: "draft" | "input" | "output" | "version" | "other";
  source: "project" | "thread";
  size: number;
  updated_at: string;
  mime_type?: string | null;
  thread_id?: string | null;
  artifact_url?: string | null;
}

export interface ProjectSummary {
  project_id: string;
  threads_count: number;
  drafts_count: number;
  inputs_count: number;
  outputs_count: number;
  versions_count: number;
  files_count: number;
  total_size: number;
  updated_at: string;
  latest_file_at?: string | null;
}

export interface ProjectDirectory {
  project_id: string;
  root_path: string;
  default_root_path: string;
  exists: boolean;
}

export interface ProjectDraftFile {
  task_name: string;
  section_name: string;
  file_path: string;
  updated_at: string;
  size: number;
}

export interface ProjectDraftVersion {
  version_id: string;
  section_name: string;
  file_path: string;
  created_at: string;
  size: number;
}

export function listProjects() {
  return apiJson<ProjectRecord[]>("/api/projects");
}

export function createProject(input: {
  name: string;
  type?: string;
  metadata?: Record<string, unknown>;
}) {
  return apiJson<ProjectRecord>("/api/projects", {
    method: "POST",
    body: jsonBody({
      name: input.name,
      type: input.type ?? "government-project-declaration",
      metadata: input.metadata ?? {},
    }),
  });
}

export function getProject(projectId: string) {
  return apiJson<ProjectRecord>(
    `/api/projects/${encodeURIComponent(projectId)}`,
  );
}

export function getProjectDirectory(projectId: string) {
  return apiJson<ProjectDirectory>(
    `/api/projects/${encodeURIComponent(projectId)}/directory`,
  );
}

export function updateProjectDirectory(
  projectId: string,
  input: { root_path?: string | null; create?: boolean },
) {
  return apiJson<ProjectDirectory>(
    `/api/projects/${encodeURIComponent(projectId)}/directory`,
    {
      method: "PUT",
      body: jsonBody({
        root_path: input.root_path ?? null,
        create: input.create ?? true,
      }),
    },
  );
}

export function selectProjectDirectory(projectId: string) {
  return apiJson<{
    project_id: string;
    root_path?: string | null;
    selected: boolean;
  }>(`/api/projects/${encodeURIComponent(projectId)}/directory/select`, {
    method: "POST",
  });
}

export function openProjectDirectory(projectId: string) {
  return apiJson<{ project_id: string; root_path: string; opened: boolean }>(
    `/api/projects/${encodeURIComponent(projectId)}/directory/open`,
    { method: "POST" },
  );
}

export function patchProject(
  projectId: string,
  input: { name?: string; status?: string; metadata?: Record<string, unknown> },
) {
  return apiJson<ProjectRecord>(
    `/api/projects/${encodeURIComponent(projectId)}`,
    {
      method: "PATCH",
      body: jsonBody(input),
    },
  );
}

export function deleteProject(projectId: string) {
  return apiJson<void>(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "DELETE",
  });
}

export function listProjectFiles(projectId: string) {
  return apiJson<{ project_id: string; files: ProjectFileNode[] }>(
    `/api/projects/${encodeURIComponent(projectId)}/files`,
  );
}

export function getProjectSummary(projectId: string) {
  return apiJson<ProjectSummary>(
    `/api/projects/${encodeURIComponent(projectId)}/summary`,
  );
}

export function readProjectFile(
  projectId: string,
  file: Pick<ProjectFileNode, "source" | "read_path" | "thread_id">,
) {
  const params = new URLSearchParams({
    path: file.read_path,
    source: file.source,
  });
  if (file.thread_id) params.set("thread_id", file.thread_id);
  return apiJson<{
    project_id: string;
    path: string;
    source: "project" | "thread";
    content: string;
    mime_type?: string | null;
    truncated?: boolean;
  }>(`/api/projects/${encodeURIComponent(projectId)}/files/read?${params}`);
}

export function uploadProjectFiles(
  projectId: string,
  files: File[],
  category: "inputs" | "outputs" | "drafts" | "files" = "inputs",
) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  const params = new URLSearchParams({ category });
  return apiJson<{
    success: boolean;
    files: ProjectFileNode[];
    message: string;
    skipped_files: string[];
  }>(`/api/projects/${encodeURIComponent(projectId)}/files/upload?${params}`, {
    method: "POST",
    body: form,
  });
}

export async function downloadProjectFile(
  projectId: string,
  file: Pick<ProjectFileNode, "source" | "read_path" | "thread_id">,
) {
  const params = new URLSearchParams({
    path: file.read_path,
    source: file.source,
  });
  if (file.thread_id) params.set("thread_id", file.thread_id);
  const response = await apiFetch(
    `/api/projects/${encodeURIComponent(projectId)}/files/download?${params}`,
  );
  if (!response.ok) throw new Error(`下载失败：HTTP ${response.status}`);
  return response.blob();
}

export async function exportProjectFilesDocx(
  projectId: string,
  files: Array<
    Pick<ProjectFileNode, "name" | "source" | "read_path" | "thread_id">
  >,
  mode: "merged" | "separate",
  title?: string,
  options: { includeImages?: boolean; modelName?: string } = {},
) {
  const response = await apiFetch(
    `/api/projects/${encodeURIComponent(projectId)}/files/export-docx`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: jsonBody({
        files: files.map((file) => ({
          path: file.read_path,
          name: file.name,
          source: file.source,
          thread_id: file.thread_id,
        })),
        mode,
        title,
        include_images: options.includeImages ?? false,
        applicant_id: "default",
        model_name: options.modelName ?? undefined,
      }),
    },
  );
  if (!response.ok) {
    const detail = await response.json().catch(() => undefined);
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `导出失败：HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.blob();
}

export function writeProjectFile(
  projectId: string,
  file: Pick<ProjectFileNode, "source" | "read_path" | "thread_id">,
  content: string,
) {
  return apiJson<ProjectFileNode>(
    `/api/projects/${encodeURIComponent(projectId)}/files/write`,
    {
      method: "PUT",
      body: jsonBody({
        path: file.read_path,
        content,
        source: file.source,
        thread_id: file.thread_id,
      }),
    },
  );
}

export function deleteProjectFile(
  projectId: string,
  file: Pick<ProjectFileNode, "source" | "read_path" | "thread_id">,
) {
  const params = new URLSearchParams({
    path: file.read_path,
    source: file.source,
  });
  if (file.thread_id) params.set("thread_id", file.thread_id);
  return apiJson<void>(
    `/api/projects/${encodeURIComponent(projectId)}/files?${params}`,
    {
      method: "DELETE",
    },
  );
}

export function listProjectDrafts(projectId: string) {
  return apiJson<{
    project_id: string;
    root_path: string;
    files: ProjectDraftFile[];
  }>(`/api/projects/${encodeURIComponent(projectId)}/drafts`);
}

function draftPath(section: string) {
  return section
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part))
    .join("/");
}

export function readProjectDraft(projectId: string, section: string) {
  return apiJson<{
    project_id: string;
    section_name: string;
    file_path: string;
    content: string;
  }>(
    `/api/projects/${encodeURIComponent(projectId)}/drafts/${draftPath(section)}`,
  );
}

export function saveProjectDraft(
  projectId: string,
  section: string,
  content: string,
) {
  return apiJson<ProjectDraftFile>(
    `/api/projects/${encodeURIComponent(projectId)}/drafts/${draftPath(section)}`,
    {
      method: "PUT",
      body: jsonBody({ content }),
    },
  );
}

export function deleteProjectDraft(projectId: string, section: string) {
  return apiJson<void>(
    `/api/projects/${encodeURIComponent(projectId)}/drafts/${draftPath(section)}`,
    { method: "DELETE" },
  );
}

export function listProjectDraftVersions(projectId: string, section: string) {
  return apiJson<{
    project_id: string;
    section_name: string;
    versions: ProjectDraftVersion[];
  }>(
    `/api/projects/${encodeURIComponent(projectId)}/draft-versions/${draftPath(section)}`,
  );
}

export function createProjectDraftVersion(projectId: string, section: string) {
  return apiJson<{
    project_id: string;
    version: ProjectDraftVersion;
  }>(
    `/api/projects/${encodeURIComponent(projectId)}/draft-versions/${draftPath(section)}`,
    {
      method: "POST",
    },
  );
}

export function readProjectDraftVersion(
  projectId: string,
  section: string,
  versionId: string,
) {
  const params = new URLSearchParams({ version_id: versionId });
  return apiJson<{
    project_id: string;
    section_name: string;
    version_id: string;
    file_path: string;
    content: string;
  }>(
    `/api/projects/${encodeURIComponent(projectId)}/draft-version-content/${draftPath(section)}?${params}`,
  );
}

export async function downloadProjectDraft(
  projectId: string,
  section: string,
  format: "markdown" | "word" = "markdown",
) {
  const endpoint =
    format === "word"
      ? `/api/projects/${encodeURIComponent(projectId)}/drafts/download-docx/${draftPath(section)}`
      : `/api/projects/${encodeURIComponent(projectId)}/drafts/download/${draftPath(section)}`;
  const response = await apiFetch(endpoint);
  if (!response.ok) throw new Error(`导出失败：HTTP ${response.status}`);
  return response.blob();
}
