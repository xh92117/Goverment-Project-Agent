"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BotIcon,
  CheckCircle2Icon,
  FileTextIcon,
  Loader2Icon,
  PlugIcon,
  PlusIcon,
  RefreshCwIcon,
  SaveIcon,
  Settings2Icon,
  UploadIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  createManagedModel,
  createMemoryFact,
  listAgents,
  loadPdfParserConfig,
  loadManagedModels,
  loadMcpConfig,
  loadMemory,
  loadMemoryConfig,
  loadSkills,
  restartChannel,
  saveMcpConfig,
  setSkillEnabled,
  testModel,
  updatePdfParserConfig,
  updateMemoryConfig,
  uploadSkill,
  listChannels,
} from "@/features/settings/api";
import type {
  ManagedModelCreateRequest,
  MCPConfig,
  PdfParserConfig,
  PdfParserConfigUpdate,
} from "@/features/settings/api";
import { modelProviderOptions } from "@/features/settings/model-providers";

type SettingsTab = "providers" | "skills" | "pdf" | "mcp" | "memory";

const tabs: Array<{
  id: SettingsTab;
  label: string;
  icon: typeof Settings2Icon;
}> = [
  { id: "providers", label: "模型供应商", icon: BotIcon },
  { id: "skills", label: "智能体技能", icon: Settings2Icon },
  { id: "pdf", label: "PDF 解析", icon: FileTextIcon },
  { id: "mcp", label: "MCP 接入", icon: PlugIcon },
  { id: "memory", label: "记忆与通道", icon: CheckCircle2Icon },
];

const emptyModel: ManagedModelCreateRequest = {
  model_name: "",
  provider: "",
  url: "",
  api_key: "",
};

const defaultPdfParserForm: PdfParserConfigUpdate = {
  api_token: "",
  clear_token: false,
  api_base_url: "https://mineru.net",
  model_version: "vlm",
  language: "ch",
  timeout_seconds: 60,
  poll_interval_seconds: 5,
  max_wait_seconds: 900,
  pdf_converter: "auto",
};

function optionalTrim(value: string | undefined) {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed;
}

function pdfParserFormFromConfig(
  config: PdfParserConfig,
): PdfParserConfigUpdate {
  return {
    api_token: "",
    clear_token: false,
    api_base_url: config.api_base_url,
    model_version: config.model_version,
    language: config.language,
    timeout_seconds: config.timeout_seconds,
    poll_interval_seconds: config.poll_interval_seconds,
    max_wait_seconds: config.max_wait_seconds,
    pdf_converter: config.pdf_converter,
  };
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const skillUploadRef = useRef<HTMLInputElement | null>(null);
  const [tab, setTab] = useState<SettingsTab>("providers");
  const [newModel, setNewModel] =
    useState<ManagedModelCreateRequest>(emptyModel);
  const [addModelOpen, setAddModelOpen] = useState(false);
  const [mcpText, setMcpText] = useState("{}");
  const [pdfParserForm, setPdfParserForm] =
    useState<PdfParserConfigUpdate>(defaultPdfParserForm);
  const [pdfParserMessage, setPdfParserMessage] = useState("");
  const [memoryFact, setMemoryFact] = useState("");
  const [testResult, setTestResult] = useState<Record<string, string>>({});

  const managedModels = useQuery({
    queryKey: ["managed-models"],
    queryFn: loadManagedModels,
  });
  const skills = useQuery({ queryKey: ["skills"], queryFn: loadSkills });
  const mcp = useQuery({ queryKey: ["mcp-config"], queryFn: loadMcpConfig });
  const pdfParser = useQuery({
    queryKey: ["pdf-parser-config"],
    queryFn: loadPdfParserConfig,
  });
  const memory = useQuery({ queryKey: ["memory"], queryFn: loadMemory });
  const memoryConfig = useQuery({
    queryKey: ["memory-config"],
    queryFn: loadMemoryConfig,
  });
  const agents = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const channels = useQuery({ queryKey: ["channels"], queryFn: listChannels });

  useEffect(() => {
    if (mcp.data) setMcpText(JSON.stringify(mcp.data, null, 2));
  }, [mcp.data]);

  useEffect(() => {
    if (pdfParser.data)
      setPdfParserForm(pdfParserFormFromConfig(pdfParser.data));
  }, [pdfParser.data]);

  const createModel = useMutation({
    mutationFn: () =>
      createManagedModel({
        model_name: newModel.model_name.trim(),
        provider: newModel.provider.trim(),
        url: optionalTrim(newModel.url),
        api_key: optionalTrim(newModel.api_key),
      }),
    onSuccess: async () => {
      setNewModel(emptyModel);
      setAddModelOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["managed-models"] });
      await queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const test = useMutation({
    mutationFn: (name: string) => testModel(name),
    onSuccess: (result) => {
      setTestResult((current) => ({
        ...current,
        [result.name]: result.ok
          ? `可用${result.latency_ms ? ` · ${result.latency_ms}ms` : ""}`
          : result.message?.trim()
            ? result.message
            : "不可用",
      }));
    },
    onError: (error, name) => {
      setTestResult((current) => ({ ...current, [name]: error.message }));
    },
  });

  const toggleSkill = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      setSkillEnabled(name, enabled),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["skills"] }),
  });

  const upload = useMutation({
    mutationFn: (file: File) => uploadSkill(file),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["skills"] }),
  });

  const saveMcp = useMutation({
    mutationFn: () => saveMcpConfig(JSON.parse(mcpText) as MCPConfig),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["mcp-config"] }),
  });

  const savePdfParser = useMutation({
    mutationFn: () => updatePdfParserConfig(pdfParserForm),
    onSuccess: async (config) => {
      setPdfParserForm(pdfParserFormFromConfig(config));
      setPdfParserMessage("已同步到后端配置");
      await queryClient.invalidateQueries({ queryKey: ["pdf-parser-config"] });
    },
    onError: (error) => {
      setPdfParserMessage(error instanceof Error ? error.message : "保存失败");
    },
  });

  const saveMemory = useMutation({
    mutationFn: () =>
      updateMemoryConfig({
        enabled: memoryConfig.data?.enabled,
        injection_enabled: memoryConfig.data?.injection_enabled,
        max_facts: memoryConfig.data?.max_facts,
        max_injection_tokens: memoryConfig.data?.max_injection_tokens,
      }),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["memory-config"] }),
  });

  const restart = useMutation({
    mutationFn: (name: string) => restartChannel(name),
    onSuccess: async () =>
      queryClient.invalidateQueries({ queryKey: ["channels"] }),
  });

  const addFact = useMutation({
    mutationFn: () => createMemoryFact(memoryFact),
    onSuccess: async () => {
      setMemoryFact("");
      await queryClient.invalidateQueries({ queryKey: ["memory"] });
    },
  });

  return (
    <main className="codex-main single">
      <header className="main-head">
        <div>
          <div className="mh-title">设置</div>
          <div className="mh-breadcrumb">模型、技能、MCP、记忆与通道配置</div>
        </div>
      </header>

      <div className="settings-view">
        <aside className="settings-nav">
          {tabs.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                type="button"
                className={`sn-item${tab === item.id ? "active" : ""}`}
                onClick={() => setTab(item.id)}
              >
                <Icon size={16} />
                {item.label}
              </button>
            );
          })}
        </aside>

        <section className="settings-content">
          {tab === "providers" ? (
            <div className="settings-panel">
              <div className="sc-title">模型供应商管理</div>
              <div className="provider-list">
                {managedModels.data?.models?.map((model) => (
                  <div key={model.name} className="provider-row">
                    <div className="provider-logo">
                      {(model.provider?.trim() ? model.provider : model.name)
                        .slice(0, 1)
                        .toUpperCase()}
                    </div>
                    <div className="provider-info">
                      <strong>
                        {model.display_name?.trim()
                          ? model.display_name
                          : model.name}
                      </strong>
                      <span>
                        {model.provider?.trim() ? model.provider : "custom"} ·{" "}
                        {model.model?.trim() ? model.model : model.name}
                      </span>
                      {testResult[model.name] ? (
                        <small>{testResult[model.name]}</small>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      className="ghost-btn"
                      onClick={() => test.mutate(model.name)}
                    >
                      {test.isPending ? (
                        <Loader2Icon size={14} className="spin" />
                      ) : (
                        <RefreshCwIcon size={14} />
                      )}
                      测试
                    </button>
                  </div>
                ))}
              </div>

              <button
                type="button"
                className="primary-btn"
                onClick={() => setAddModelOpen((current) => !current)}
                aria-expanded={addModelOpen}
              >
                <PlusIcon size={15} />
                新增模型
              </button>
              {addModelOpen ? (
                <div className="add-model-menu">
                  <div className="form-grid add-model-form">
                    <select
                      aria-label="模型供应商"
                      value={newModel.provider}
                      onChange={(event) => {
                        const provider = modelProviderOptions.find(
                          (item) => item.value === event.target.value,
                        );
                        setNewModel((model) => ({
                          ...model,
                          provider: event.target.value,
                          url: provider?.url ?? "",
                        }));
                      }}
                    >
                      <option value="">选择模型供应商</option>
                      {modelProviderOptions.map((provider) => (
                        <option key={provider.value} value={provider.value}>
                          {provider.label}
                        </option>
                      ))}
                    </select>
                    <input
                      placeholder="模型名称"
                      value={newModel.model_name}
                      onChange={(event) =>
                        setNewModel((model) => ({
                          ...model,
                          model_name: event.target.value,
                        }))
                      }
                    />
                    <input
                      placeholder="URL"
                      value={newModel.url ?? ""}
                      onChange={(event) =>
                        setNewModel((model) => ({
                          ...model,
                          url: event.target.value,
                        }))
                      }
                    />
                    <input
                      placeholder="API Key"
                      type="password"
                      value={newModel.api_key ?? ""}
                      onChange={(event) =>
                        setNewModel((model) => ({
                          ...model,
                          api_key: event.target.value,
                        }))
                      }
                    />
                  </div>
                  <div className="add-model-actions">
                    <button
                      type="button"
                      className="primary-btn"
                      onClick={() => createModel.mutate()}
                      disabled={
                        !newModel.model_name.trim() ||
                        !newModel.provider.trim() ||
                        createModel.isPending
                      }
                    >
                      {createModel.isPending ? (
                        <Loader2Icon size={15} className="spin" />
                      ) : (
                        <SaveIcon size={15} />
                      )}
                      保存模型
                    </button>
                    <button
                      type="button"
                      className="ghost-btn"
                      onClick={() => {
                        setNewModel(emptyModel);
                        setAddModelOpen(false);
                      }}
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {tab === "skills" ? (
            <div className="settings-panel">
              <div className="sc-title">智能体技能</div>
              <div className="skill-grid">
                {skills.data?.skills?.map((skill) => (
                  <div key={skill.name} className="skill-card">
                    <div className="skill-head">
                      <div className="skill-icon">
                        <Settings2Icon size={16} />
                      </div>
                      <div>
                        <div className="skill-name">{skill.name}</div>
                        <div className="skill-desc">
                          {skill.description?.trim()
                            ? skill.description
                            : skill.category?.trim()
                              ? skill.category
                              : "暂无说明"}
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      className={`switch ${skill.enabled !== false ? "on" : ""}`}
                      aria-label="启停技能"
                      onClick={() =>
                        toggleSkill.mutate({
                          name: skill.name,
                          enabled: skill.enabled === false,
                        })
                      }
                    />
                  </div>
                ))}
                <button
                  type="button"
                  className="add-skill"
                  onClick={() => skillUploadRef.current?.click()}
                >
                  <UploadIcon size={18} />
                  上传技能包
                </button>
              </div>
              <input
                ref={skillUploadRef}
                type="file"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) upload.mutate(file);
                  event.currentTarget.value = "";
                }}
              />
            </div>
          ) : null}

          {tab === "pdf" ? (
            <div className="settings-panel">
              <div className="sc-title">PDF 解析</div>

              <div className="settings-status-row">
                <div className="provider-info">
                  <strong>MinerU</strong>
                  <span>
                    {pdfParser.data?.token_configured
                      ? "Token 已配置"
                      : "Token 未配置"}{" "}
                    · {pdfParserForm.model_version || "vlm"} ·{" "}
                    {pdfParserForm.language || "ch"}
                  </span>
                </div>
                {pdfParser.isFetching ? (
                  <Loader2Icon size={15} className="spin" />
                ) : null}
              </div>

              <div className="form-grid pdf-parser-form">
                <label className="settings-field full">
                  <span>API Token</span>
                  <input
                    type="password"
                    value={pdfParserForm.api_token ?? ""}
                    placeholder={
                      pdfParser.data?.token_configured
                        ? "已配置，留空保留当前 Token"
                        : "MinerU API Token"
                    }
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        api_token: event.target.value,
                        clear_token: false,
                      }));
                    }}
                  />
                </label>

                <label className="settings-field full">
                  <span>API Base URL</span>
                  <input
                    value={pdfParserForm.api_base_url}
                    placeholder="https://mineru.net"
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        api_base_url: event.target.value,
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>模型版本</span>
                  <input
                    value={pdfParserForm.model_version}
                    placeholder="vlm"
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        model_version: event.target.value,
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>语言</span>
                  <input
                    value={pdfParserForm.language}
                    placeholder="ch"
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        language: event.target.value,
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>请求超时（秒）</span>
                  <input
                    type="number"
                    min={1}
                    max={600}
                    value={pdfParserForm.timeout_seconds}
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        timeout_seconds: Number(event.target.value),
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>轮询间隔（秒）</span>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    value={pdfParserForm.poll_interval_seconds}
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        poll_interval_seconds: Number(event.target.value),
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>最长等待（秒）</span>
                  <input
                    type="number"
                    min={30}
                    max={7200}
                    value={pdfParserForm.max_wait_seconds}
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        max_wait_seconds: Number(event.target.value),
                      }));
                    }}
                  />
                </label>

                <label className="settings-field">
                  <span>转换策略</span>
                  <select
                    value={pdfParserForm.pdf_converter}
                    onChange={(event) => {
                      setPdfParserMessage("");
                      setPdfParserForm((form) => ({
                        ...form,
                        pdf_converter: event.target
                          .value as PdfParserConfigUpdate["pdf_converter"],
                      }));
                    }}
                  >
                    <option value="auto">auto</option>
                    <option value="pymupdf4llm">pymupdf4llm</option>
                    <option value="markitdown">markitdown</option>
                  </select>
                </label>
              </div>

              <div className="settings-actions-row">
                <button
                  type="button"
                  className="primary-btn"
                  onClick={() => savePdfParser.mutate()}
                  disabled={
                    savePdfParser.isPending ||
                    !pdfParserForm.api_base_url.trim() ||
                    !pdfParserForm.model_version.trim() ||
                    !pdfParserForm.language.trim()
                  }
                >
                  {savePdfParser.isPending ? (
                    <Loader2Icon size={15} className="spin" />
                  ) : (
                    <SaveIcon size={15} />
                  )}
                  保存 PDF 解析配置
                </button>
                {pdfParser.data?.token_configured ? (
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => {
                      setPdfParserMessage("保存后清空 Token");
                      setPdfParserForm((form) => ({
                        ...form,
                        api_token: "",
                        clear_token: true,
                      }));
                    }}
                  >
                    清空 Token
                  </button>
                ) : null}
                {pdfParserMessage ? (
                  <span className="settings-inline-message">
                    {pdfParserMessage}
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}

          {tab === "mcp" ? (
            <div className="settings-panel">
              <div className="sc-title">MCP 接入</div>
              <textarea
                className="json-editor"
                value={mcpText}
                onChange={(event) => setMcpText(event.target.value)}
              />
              <button
                type="button"
                className="primary-btn"
                onClick={() => saveMcp.mutate()}
                disabled={saveMcp.isPending}
              >
                <SaveIcon size={15} />
                保存 MCP 配置
              </button>
            </div>
          ) : null}

          {tab === "memory" ? (
            <div className="settings-panel">
              <div className="sc-title">记忆与通道</div>
              <div className="provider-row">
                <div className="provider-info">
                  <strong>记忆注入</strong>
                  <span>
                    {memoryConfig.data?.enabled ? "已启用" : "未启用"} ·{" "}
                    {memory.data?.facts?.length ?? 0} 条事实
                  </span>
                </div>
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => saveMemory.mutate()}
                >
                  <SaveIcon size={14} />
                  保存
                </button>
              </div>
              <input
                value={memoryFact}
                placeholder="新增一条用户记忆事实"
                onChange={(event) => setMemoryFact(event.target.value)}
              />
              <button
                type="button"
                className="primary-btn"
                onClick={() => addFact.mutate()}
                disabled={!memoryFact.trim() || addFact.isPending}
              >
                <PlusIcon size={15} />
                新增记忆
              </button>

              <div className="sc-title small">智能体</div>
              <div className="provider-list">
                {agents.data?.agents?.map((agent) => (
                  <div key={agent.name} className="mcp-row">
                    <span className="mcp-dot" />
                    <div>
                      <strong>{agent.name}</strong>
                      <span>
                        {agent.model?.trim() ? agent.model : "默认模型"} ·{" "}
                        {(agent.tools ?? []).length} 个工具
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className="sc-title small">通道</div>
              <div className="provider-list">
                {channels.data?.channels?.map((channel) => (
                  <div key={channel.name} className="mcp-row">
                    <span
                      className={`mcp-dot ${channel.enabled === false ? "off" : ""}`}
                    />
                    <div>
                      <strong>{channel.name}</strong>
                      <span>
                        {channel.status?.trim()
                          ? channel.status
                          : channel.enabled === false
                            ? "disabled"
                            : "enabled"}
                      </span>
                    </div>
                    <button
                      type="button"
                      className="ghost-btn"
                      onClick={() => restart.mutate(channel.name)}
                    >
                      <RefreshCwIcon size={14} />
                      重启
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
