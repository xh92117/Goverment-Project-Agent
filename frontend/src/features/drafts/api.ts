import { apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface ProposalDraftFile {
  task_name: string;
  section_name: string;
  file_path?: string;
  path?: string;
  updated_at?: string;
  size?: number;
}

export interface ProposalDraftList {
  root_path?: string;
  tasks?: Record<string, ProposalDraftFile[]>;
  files?: ProposalDraftFile[];
}

export type DraftDownloadFormat = "markdown" | "word";

function groupByTask(files: ProposalDraftFile[] = []) {
  return files.reduce<Record<string, ProposalDraftFile[]>>((groups, file) => {
    const key = file.task_name || "未命名项目";
    groups[key] = [...(groups[key] ?? []), file];
    return groups;
  }, {});
}

function draftPath(task: string, section: string) {
  const encodedTask = encodeURIComponent(task);
  const encodedSection = section
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `${encodedTask}/${encodedSection}`;
}

export async function listDrafts() {
  const data = await apiJson<ProposalDraftList>("/api/proposal-drafts");
  const files = data.files ?? Object.values(data.tasks ?? {}).flat();
  return {
    ...data,
    files,
    tasks: data.tasks ?? groupByTask(files),
  };
}

export function readDraft(task: string, section: string) {
  return apiJson<{ content: string; task_name: string; section_name: string }>(
    `/api/proposal-drafts/${draftPath(task, section)}`,
  );
}

export function saveDraft(task: string, section: string, content: string) {
  return apiJson<{ task_name: string; section_name: string; file_path?: string; size?: number }>(
    `/api/proposal-drafts/${draftPath(task, section)}`,
    {
      method: "PUT",
      body: jsonBody({ content }),
    },
  );
}

export function deleteDraft(task: string, section: string) {
  return apiJson<void>(`/api/proposal-drafts/${draftPath(task, section)}`, {
    method: "DELETE",
  });
}

export function listDraftVersions(task: string, section: string) {
  return apiJson<{
    versions: Array<{ version_id: string; created_at?: string; file_path?: string; size?: number }>;
  }>(`/api/proposal-drafts/versions/${draftPath(task, section)}`);
}

export function createDraftVersion(task: string, section: string) {
  return apiJson<{ version: { version_id: string; file_path?: string; created_at?: string } }>(
    `/api/proposal-drafts/versions/${draftPath(task, section)}`,
    { method: "POST" },
  );
}

export function readDraftVersion(task: string, section: string, versionId: string) {
  return apiJson<{
    content: string;
    task_name: string;
    section_name: string;
    version_id: string;
    file_path?: string;
  }>(
    `/api/proposal-drafts/version-content/${draftPath(task, section)}?version_id=${encodeURIComponent(versionId)}`,
  );
}

export async function downloadDraft(
  task: string,
  section: string,
  format: DraftDownloadFormat = "markdown",
) {
  const endpoint =
    format === "word"
      ? `/api/proposal-drafts/download-docx/${draftPath(task, section)}`
      : `/api/proposal-drafts/download/${draftPath(task, section)}`;
  const response = await apiFetch(endpoint);
  if (!response.ok) {
    throw new Error(`导出失败：HTTP ${response.status}`);
  }
  return response.blob();
}
