import { apiFetch, apiJson, jsonBody } from "@/shared/api/client";

export interface KnowledgeIndexEntry {
  index_id: string;
  title: string;
  entry_type?: string;
  file_path: string;
  folder_path?: string | null;
  category?: string;
  domain?: string;
  summary?: string;
  keywords?: string[];
  technical_terms?: string[];
  methods?: string[];
  research_objects?: string[];
  proposal_sections?: string[];
  evidence_type?: string | null;
  evidence_id?: string | null;
  asset_ids?: string[];
  applicant_id?: string | null;
  verification_status?: "needs_review" | "human_verified" | "rejected" | null;
  valid_from?: string | null;
  valid_to?: string | null;
  source_file_path?: string | null;
  source_anchor?: string | null;
  chunk_file_path?: string | null;
  project_types?: string[];
  metadata?: Record<string, unknown>;
  recommended_sections?: Array<{
    heading: string;
    anchor?: string;
    summary?: string;
  }>;
  confidence?: number;
  updated_at?: string;
}

export interface KnowledgeIndexSearchHit {
  entry: KnowledgeIndexEntry;
  score?: number;
  matched_fields?: string[];
}

export interface KnowledgeIndexBuildResult {
  scanned_files: number;
  created: number;
  updated: number;
  reused?: number;
  skipped: number;
  deleted?: number;
  document_entries?: number;
  section_entries?: number;
  chunk_files_created?: number;
  deduplicated_files?: string[];
  version_backup_path?: string | null;
  parser_counts?: Record<string, number>;
  parse_errors?: Array<{
    file_path?: string;
    stage?: string;
    error?: string;
  }>;
  warnings?: string[];
  scale_stats?: {
    source_files_scanned?: number;
    index_entries_total?: number;
    document_entries_total?: number;
    section_entries_total?: number;
    chunk_files_total?: number;
    index_json_bytes?: number;
    sqlite_index_enabled?: boolean;
    sqlite_index_bytes?: number;
    elapsed_seconds?: number;
  };
}

export interface KnowledgeIndexPageResult {
  entries: KnowledgeIndexEntry[];
  total: number;
  offset: number;
  limit: number;
}

export interface KnowledgeRecallEvalCase {
  query: string;
  expected_file_paths?: string[];
  expected_index_ids?: string[];
  expected_categories?: string[];
}

export interface KnowledgeRecallEvalResult {
  cases: Array<{
    query: string;
    expected_count: number;
    hit: boolean;
    first_rank?: number | null;
    reciprocal_rank: number;
    top_results: KnowledgeIndexSearchHit[];
  }>;
  total_cases: number;
  hit_count: number;
  recall_at_k: number;
  mrr: number;
}

export interface KnowledgeDocument {
  document_id: string;
  title?: string;
  library?: string;
  doc_type?: string;
  source_uri?: string;
  metadata?: Record<string, unknown>;
}

export interface KnowledgeUploadedFile {
  filename: string;
  size: number;
  file_path: string;
  incoming_path: string;
  extension?: string | null;
  original_filename?: string | null;
  asset_id?: string | null;
  evidence_id?: string | null;
  deduplicated?: boolean | null;
}

export type KnowledgeVerificationStatus =
  | "needs_review"
  | "human_verified"
  | "rejected";

export interface KnowledgeEvidence {
  evidence_id: string;
  applicant_id: string;
  asset_ids: string[];
  evidence_type: string;
  suggested_evidence_type?: string | null;
  title: string;
  holder?: string | null;
  issuer?: string | null;
  certificate_no?: string | null;
  issued_at?: string | null;
  valid_from?: string | null;
  valid_to?: string | null;
  ocr_text: string;
  visual_summary: string;
  keywords: string[];
  applicable_chapters: string[];
  project_tags: string[];
  verification_status: KnowledgeVerificationStatus;
  extraction_confidence: number;
  extraction_status: "pending" | "partial" | "completed" | "failed";
  extraction_provider?: string | null;
  extraction_warnings: string[];
  review_notes: string;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  confidentiality_level: string;
  created_at: string;
  updated_at: string;
}

export type KnowledgeEvidencePatch = Partial<
  Pick<
    KnowledgeEvidence,
    | "evidence_type"
    | "title"
    | "holder"
    | "issuer"
    | "certificate_no"
    | "issued_at"
    | "valid_from"
    | "valid_to"
    | "ocr_text"
    | "visual_summary"
    | "keywords"
    | "applicable_chapters"
    | "project_tags"
    | "verification_status"
    | "review_notes"
    | "confidentiality_level"
  >
>;

export interface KnowledgeFileDeleteResult {
  success: boolean;
  file_path: string;
  delete_source: boolean;
  deleted_files: string[];
  missing_files?: string[];
  deleted_index_ids: string[];
  deleted_index_entries: number;
  version_backup_path?: string | null;
  message: string;
}

export interface KnowledgeFileSaveResult {
  file_path: string;
  resolved_path?: string;
  anchor?: string | null;
  bytes_written: number;
  saved: boolean;
}

export interface KnowledgeImageModelOption {
  name: string;
  display_name?: string | null;
  provider?: string | null;
  model?: string | null;
}

export interface KnowledgeImageModelSettings {
  selected_model?: string | null;
  selected_model_valid: boolean;
  vision_models: KnowledgeImageModelOption[];
}

export interface KnowledgeImageModelCreateRequest {
  model_name: string;
  provider: string;
  api_key?: string;
  url?: string;
}

export function loadKnowledgeImageModelSettings() {
  return apiJson<KnowledgeImageModelSettings>(
    "/api/settings/knowledge-image-model",
  );
}

export function updateKnowledgeImageModelSettings(modelName: string) {
  return apiJson<KnowledgeImageModelSettings>(
    "/api/settings/knowledge-image-model",
    {
      method: "PUT",
      body: jsonBody({ model_name: modelName }),
    },
  );
}

export function createKnowledgeImageModel(
  model: KnowledgeImageModelCreateRequest,
) {
  return apiJson<{
    models: Array<KnowledgeImageModelOption & { supports_vision?: boolean }>;
  }>("/api/models/config", {
    method: "POST",
    body: jsonBody({ ...model, supports_vision: true }),
  });
}

export function listKnowledgeDocuments(library?: string, docType?: string) {
  const params = new URLSearchParams();
  if (library) params.set("library", library);
  if (docType) params.set("doc_type", docType);
  return apiJson<KnowledgeDocument[]>(
    `/api/knowledge/documents${params.size ? `?${params}` : ""}`,
  );
}

export function deleteKnowledgeDocument(documentId: string) {
  return apiJson<void>(
    `/api/knowledge/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
    },
  );
}

export function deleteKnowledgeFile(filePath: string, deleteSource = true) {
  const params = new URLSearchParams({
    file_path: filePath,
    delete_source: String(deleteSource),
  });
  return apiJson<KnowledgeFileDeleteResult>(`/api/knowledge/files?${params}`, {
    method: "DELETE",
  });
}

export function deleteKnowledgeEvidence(
  evidenceId: string,
  applicantId: string,
) {
  const params = new URLSearchParams({ applicant_id: applicantId });
  return apiJson<{
    success: boolean;
    evidence_id: string;
    deleted_asset_ids?: string[];
  }>(`/api/knowledge/evidence/${encodeURIComponent(evidenceId)}?${params}`, {
    method: "DELETE",
  });
}

export function listKnowledgeEvidence(applicantId: string, query = "") {
  const params = new URLSearchParams({
    applicant_id: applicantId,
    limit: "100",
  });
  if (query.trim()) params.set("query", query.trim());
  return apiJson<KnowledgeEvidence[]>(`/api/knowledge/evidence?${params}`);
}

export function updateKnowledgeEvidence(
  evidenceId: string,
  applicantId: string,
  patch: KnowledgeEvidencePatch,
) {
  const params = new URLSearchParams({ applicant_id: applicantId });
  return apiJson<KnowledgeEvidence>(
    `/api/knowledge/evidence/${encodeURIComponent(evidenceId)}?${params}`,
    { method: "PATCH", body: jsonBody(patch) },
  );
}

export function extractKnowledgeEvidence(
  evidenceId: string,
  applicantId: string,
) {
  const params = new URLSearchParams({ applicant_id: applicantId });
  return apiJson<KnowledgeEvidence>(
    `/api/knowledge/evidence/${encodeURIComponent(evidenceId)}/extract?${params}`,
    { method: "POST" },
  );
}

export function batchReviewKnowledgeEvidence(
  evidenceIds: string[],
  verificationStatus: "human_verified" | "rejected",
  applicantId = "default",
  reviewNotes = "",
) {
  return apiJson<{
    updated: KnowledgeEvidence[];
    skipped: Record<string, string>;
  }>("/api/knowledge/evidence/batch-review", {
    method: "POST",
    body: jsonBody({
      applicant_id: applicantId,
      evidence_ids: evidenceIds,
      verification_status: verificationStatus,
      review_notes: reviewNotes,
    }),
  });
}

export function knowledgeAssetContentUrl(
  assetId: string,
  applicantId: string,
  thumbnail = false,
) {
  const params = new URLSearchParams({ applicant_id: applicantId });
  if (thumbnail) params.set("thumbnail", "true");
  return `/api/knowledge/assets/${encodeURIComponent(assetId)}/content?${params}`;
}

export function listKnowledgeIndex(category?: string) {
  const suffix = category ? `?category=${encodeURIComponent(category)}` : "";
  return apiJson<KnowledgeIndexEntry[]>(`/api/knowledge/index${suffix}`);
}

export function listKnowledgeIndexPage(
  category?: string,
  offset = 0,
  limit = 100,
  query = "",
) {
  return apiJson<KnowledgeIndexPageResult>("/api/knowledge/index/page", {
    method: "POST",
    body: jsonBody({
      category: category ?? null,
      offset,
      limit,
      query,
    }),
  });
}

export function searchKnowledgeIndex(
  query: string,
  category?: string,
  limit = 20,
) {
  return apiJson<{
    results: KnowledgeIndexSearchHit[];
    count?: number;
  }>("/api/knowledge/index/search", {
    method: "POST",
    body: jsonBody({
      query,
      categories: category ? [category] : undefined,
      search_mode: "hybrid",
      limit,
    }),
  });
}

export function evaluateKnowledgeRecall(
  cases: KnowledgeRecallEvalCase[],
  category?: string,
  limit = 10,
) {
  return apiJson<KnowledgeRecallEvalResult>("/api/knowledge/index/evaluate", {
    method: "POST",
    body: jsonBody({
      cases,
      category: category ?? null,
      limit,
      search_mode: "hybrid",
    }),
  });
}

export function readKnowledgeFile(filePath: string, anchor?: string | null) {
  return apiJson<{ content: string; truncated?: boolean; file_path?: string }>(
    "/api/knowledge/files/read",
    {
      method: "POST",
      body: jsonBody({
        file_path: filePath,
        anchor: anchor ?? null,
        max_chars: 14_000,
      }),
    },
  );
}

export function saveKnowledgeFile(
  filePath: string,
  content: string,
  anchor?: string | null,
) {
  return apiJson<KnowledgeFileSaveResult>("/api/knowledge/files/save", {
    method: "PUT",
    body: jsonBody({
      file_path: filePath,
      content,
      anchor: anchor ?? null,
    }),
  });
}

export function buildKnowledgeIndex(folderPath?: string) {
  return apiJson<KnowledgeIndexBuildResult>("/api/knowledge/index/build", {
    method: "POST",
    body: jsonBody({
      folder_path: folderPath ?? "",
      recursive: true,
      replace_existing: true,
      incremental: true,
      project_types: ["科研项目申报"],
    }),
  });
}

export function incrementalUpdateKnowledge() {
  return apiJson<{
    organization?: { scanned?: number; moved?: number };
    index_build: KnowledgeIndexBuildResult;
  }>("/api/knowledge/index/incremental-update", {
    method: "POST",
    body: jsonBody({
      organize_incoming: true,
      incoming_path: "_incoming",
      folder_path: "",
      recursive: true,
      replace_existing: true,
      dry_run: false,
      default_category: "未分类",
      default_domain: "通用",
      incremental: true,
      project_types: ["科研项目申报"],
    }),
  });
}

export function processIncomingAndBuildKnowledgeIndex() {
  return apiJson<{
    organization?: { scanned?: number; moved?: number };
    index_build: KnowledgeIndexBuildResult;
  }>("/api/knowledge/index/process-incoming", {
    method: "POST",
    body: jsonBody({
      incoming_path: "_incoming",
      folder_path: "",
      recursive: true,
      replace_existing: true,
      dry_run: false,
      default_category: "未分类",
      default_domain: "通用",
      incremental: true,
      project_types: ["科研项目申报"],
    }),
  });
}

export function uploadKnowledgeFiles(
  files: File[],
  incomingPath = "_incoming",
  applicantId = "default",
  evidenceType = "image_evidence",
) {
  const params = new URLSearchParams({
    incoming_path: incomingPath,
    applicant_id: applicantId,
    evidence_type: evidenceType,
  });
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return apiJson<{
    success: boolean;
    files: KnowledgeUploadedFile[];
    message: string;
    skipped_files?: string[];
    warnings?: string[];
  }>(`/api/knowledge/files/upload?${params}`, {
    method: "POST",
    body: form,
  });
}

export async function downloadKnowledgeFile(filePath: string) {
  const params = new URLSearchParams({ file_path: filePath });
  const response = await apiFetch(`/api/knowledge/files/download?${params}`);
  if (!response.ok) {
    const detail = await response.json().catch(() => undefined);
    const message =
      typeof detail === "object" && detail && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `请求失败：HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.blob();
}
