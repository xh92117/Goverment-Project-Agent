import { apiJson, jsonBody } from "@/shared/api/client";

export interface ModelInfo {
  name: string;
  model?: string;
  display_name?: string;
  description?: string;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  provider?: string;
}

export interface ManagedModel {
  name: string;
  provider?: string;
  model?: string;
  api_key?: string;
  base_url?: string;
  display_name?: string;
  description?: string;
  supports_thinking?: boolean;
  supports_reasoning_effort?: boolean;
  supports_vision?: boolean;
  max_tokens?: number;
  temperature?: number;
  request_timeout?: number;
  max_retries?: number;
  use?: string;
}

export interface ManagedModelCreateRequest {
  model_name: string;
  provider: string;
  api_key?: string;
  url?: string;
}

export interface Skill {
  name: string;
  description?: string;
  category?: string;
  enabled?: boolean;
}

export interface MemoryFact {
  id: string;
  text?: string;
  content?: string;
  category?: string;
}

export interface MemoryConfig {
  enabled: boolean;
  storage_path: string;
  debounce_seconds: number;
  max_facts: number;
  fact_confidence_threshold: number;
  injection_enabled: boolean;
  max_injection_tokens: number;
}

export type MemoryConfigPatch = Partial<
  Pick<
    MemoryConfig,
    | "enabled"
    | "debounce_seconds"
    | "max_facts"
    | "fact_confidence_threshold"
    | "injection_enabled"
    | "max_injection_tokens"
  >
>;

export interface MCPConfig {
  mcp_servers?: Record<string, unknown>;
  servers?: Record<string, unknown>;
  mcpServers?: Record<string, unknown>;
  [key: string]: unknown;
}

export type PdfConverter = "auto" | "pymupdf4llm" | "markitdown";

export interface PdfParserConfig {
  api_token: string;
  token_configured: boolean;
  api_base_url: string;
  model_version: string;
  language: string;
  timeout_seconds: number;
  poll_interval_seconds: number;
  max_wait_seconds: number;
  pdf_converter: PdfConverter;
  env_path: string;
  config_path: string;
}

export interface PdfParserConfigUpdate {
  api_token?: string;
  clear_token?: boolean;
  api_base_url: string;
  model_version: string;
  language: string;
  timeout_seconds: number;
  poll_interval_seconds: number;
  max_wait_seconds: number;
  pdf_converter: PdfConverter;
}

export interface RuntimePathConfig {
  gp_agent_home: string;
  runtime_home: string;
  workspace_root: string;
  knowledge_root: string;
  drafts_root: string;
  projects_root: string;
  logs_root: string;
  env_path: string;
  restart_required: boolean;
}

export type RuntimePathConfigUpdate = Pick<
  RuntimePathConfig,
  | "gp_agent_home"
  | "runtime_home"
  | "workspace_root"
  | "knowledge_root"
  | "drafts_root"
  | "projects_root"
  | "logs_root"
>;

export interface Agent {
  name: string;
  description?: string;
  tools?: string[];
  model?: string;
}

export function loadModels() {
  return apiJson<{ models: ModelInfo[]; token_usage?: { enabled: boolean } }>(
    "/api/models",
  );
}

export function loadManagedModels() {
  return apiJson<{ models: ManagedModel[] }>("/api/models/config");
}

export function createManagedModel(model: ManagedModelCreateRequest) {
  return apiJson<{ models: ManagedModel[] }>("/api/models/config", {
    method: "POST",
    body: jsonBody(model),
  });
}

export function testModel(name: string) {
  return apiJson<{
    name: string;
    ok: boolean;
    latency_ms?: number;
    message?: string;
  }>(`/api/models/${encodeURIComponent(name)}/test`, {
    method: "POST",
    body: jsonBody({ timeout_seconds: 30, prompt: "Reply with OK." }),
  });
}

export function loadSkills() {
  return apiJson<{ skills: Skill[] }>("/api/skills");
}

export function setSkillEnabled(name: string, enabled: boolean) {
  return apiJson<unknown>(`/api/skills/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: jsonBody({ enabled }),
  });
}

export function uploadSkill(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiJson<{ success: boolean; skill_name: string; message: string }>(
    "/api/skills/upload",
    {
      method: "POST",
      body: form,
    },
  );
}

export function loadMemory() {
  return apiJson<{ facts?: MemoryFact[]; [key: string]: unknown }>(
    "/api/memory",
  );
}

export function loadMemoryConfig() {
  return apiJson<MemoryConfig>("/api/memory/config");
}

export function updateMemoryConfig(config: MemoryConfigPatch) {
  return apiJson<MemoryConfig>("/api/memory/config", {
    method: "PATCH",
    body: jsonBody(config),
  });
}

export function createMemoryFact(content: string) {
  return apiJson<unknown>("/api/memory/facts", {
    method: "POST",
    body: jsonBody({ content }),
  });
}

export function deleteMemoryFact(id: string) {
  return apiJson<unknown>(`/api/memory/facts/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export function clearMemory() {
  return apiJson<unknown>("/api/memory", { method: "DELETE" });
}

export function loadMcpConfig() {
  return apiJson<MCPConfig>("/api/mcp/config");
}

export function saveMcpConfig(config: MCPConfig) {
  return apiJson<unknown>("/api/mcp/config", {
    method: "PUT",
    body: jsonBody(config),
  });
}

export function loadPdfParserConfig() {
  return apiJson<PdfParserConfig>("/api/settings/pdf-parser");
}

export function updatePdfParserConfig(config: PdfParserConfigUpdate) {
  return apiJson<PdfParserConfig>("/api/settings/pdf-parser", {
    method: "PUT",
    body: jsonBody(config),
  });
}

export function loadRuntimePathConfig() {
  return apiJson<RuntimePathConfig>("/api/settings/runtime-paths");
}

export function updateRuntimePathConfig(config: RuntimePathConfigUpdate) {
  return apiJson<RuntimePathConfig>("/api/settings/runtime-paths", {
    method: "PUT",
    body: jsonBody(config),
  });
}

export function listAgents() {
  return apiJson<{ agents: Agent[] }>("/api/agents");
}

export function listChannels() {
  return apiJson<{
    channels?: Array<{ name: string; enabled?: boolean; status?: string }>;
  }>("/api/channels/");
}

export function restartChannel(name: string) {
  return apiJson<unknown>(`/api/channels/${encodeURIComponent(name)}/restart`, {
    method: "POST",
  });
}
