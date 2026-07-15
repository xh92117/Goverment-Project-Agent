"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3Icon,
  ChevronDownIcon,
  ChevronRightIcon,
  DownloadIcon,
  EyeIcon,
  FileTextIcon,
  FolderIcon,
  ImageIcon,
  Loader2Icon,
  PencilIcon,
  RefreshCwIcon,
  SaveIcon,
  SearchIcon,
  Settings2Icon,
  Trash2Icon,
  UploadIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { MarkdownRenderer } from "@/features/chat/markdown-renderer";
import {
  batchReviewKnowledgeEvidence,
  buildKnowledgeIndex,
  createKnowledgeImageModel,
  deleteKnowledgeFile,
  deleteKnowledgeEvidence,
  downloadKnowledgeFile,
  evaluateKnowledgeRecall,
  listKnowledgeIndexPage,
  loadKnowledgeImageModelSettings,
  processIncomingAndBuildKnowledgeIndex,
  readKnowledgeFile,
  saveKnowledgeFile,
  searchKnowledgeIndex,
  updateKnowledgeImageModelSettings,
  uploadKnowledgeFiles,
} from "@/features/knowledge/api";
import type {
  KnowledgeImageModelCreateRequest,
  KnowledgeIndexEntry,
  KnowledgeIndexSearchHit,
} from "@/features/knowledge/api";
import { modelProviderOptions } from "@/features/settings/model-providers";
import { formatDateTime } from "@/shared/lib/format";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function fileName(path: string) {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function preferredText(value: string | null | undefined, fallback: string) {
  const trimmed = value?.trim();
  if (trimmed) return trimmed;
  return fallback;
}

function optionalTrim(value: string | undefined) {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed;
}

function formatBytes(value?: number) {
  if (!value || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size >= 10 || unitIndex === 0 ? Math.round(size) : size.toFixed(1)} ${units[unitIndex]}`;
}

function entryFilePath(entry: KnowledgeIndexEntry) {
  return entry.source_file_path?.trim()
    ? entry.source_file_path
    : entry.file_path;
}

function entryPreviewPath(entry: KnowledgeIndexEntry) {
  return entry.chunk_file_path?.trim()
    ? entry.chunk_file_path
    : entry.file_path;
}

function isGeneratedChunk(entry: KnowledgeIndexEntry) {
  return [
    Boolean(entry.chunk_file_path?.trim()),
    entry.file_path.startsWith("申报书章节分块/"),
    Boolean(entry.metadata?.chunk_kind),
  ].some((flag) => flag);
}

function chunkOrder(entry: KnowledgeIndexEntry) {
  const value = entry.metadata?.chunk_order;
  return typeof value === "number" ? value : Number.MAX_SAFE_INTEGER;
}

function entryContentKind(entry: KnowledgeIndexEntry) {
  const contentRole = entry.metadata?.content_role;
  if (typeof contentRole === "string" && contentRole.trim()) return contentRole;
  const chunkKind = entry.metadata?.chunk_kind;
  if (typeof chunkKind === "string" && chunkKind.trim()) return chunkKind;
  return entry.entry_type ?? "条目";
}

function entryFileTitle(entry: KnowledgeIndexEntry) {
  return fileName(entryFilePath(entry));
}

function isEditableKnowledgePath(path: string) {
  return /\.(md|markdown|txt)$/i.test(path);
}

function boundedSearchScore(score?: number) {
  if (typeof score !== "number" || !Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, score));
}

function formatSearchScore(score?: number) {
  const value = boundedSearchScore(score);
  return value >= 10 ? value.toFixed(0) : value.toFixed(1);
}

const DEFAULT_CATEGORIES = [
  "申报书模板",
  "历史申报书",
  "国内外研究现状",
  "已有研究基础",
  "团队成果",
  "政策指南",
  "技术路线",
  "创新点",
  "预算依据",
  "未分类",
];

const DEFAULT_RECALL_EVAL_CASES = [
  { query: "申报条件与材料要求", expected_categories: ["政策指南"] },
  { query: "经费预算说明和预算科目", expected_categories: ["预算依据"] },
  {
    query: "已有研究基础和前期工作",
    expected_categories: ["已有研究基础", "历史申报书"],
  },
  { query: "团队论文专利成果", expected_categories: ["团队成果"] },
  {
    query: "技术路线和实施方案",
    expected_categories: ["技术路线", "历史申报书"],
  },
];

const INDEX_PAGE_SIZE = 100;

const EMPTY_IMAGE_MODEL_FORM: KnowledgeImageModelCreateRequest = {
  model_name: "",
  provider: "",
  url: "",
  api_key: "",
};

export function KnowledgePage() {
  const queryClient = useQueryClient();
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<KnowledgeIndexEntry | null>(null);
  const [searchResults, setSearchResults] = useState<
    KnowledgeIndexSearchHit[] | null
  >(null);
  const [lastSearchQuery, setLastSearchQuery] = useState("");
  const [recallQuery, setRecallQuery] = useState("");
  const [lastRecallQuery, setLastRecallQuery] = useState("");
  const [previewMode, setPreviewMode] = useState<"preview" | "edit">("preview");
  const [draftContent, setDraftContent] = useState("");
  const [expandedTree, setExpandedTree] = useState<Set<string>>(
    new Set(["type:未分类"]),
  );
  const [pageOffset, setPageOffset] = useState(0);
  const [imageModelDialogOpen, setImageModelDialogOpen] = useState(false);
  const [imageModelDraft, setImageModelDraft] = useState<string | null>(null);
  const [imageModelForm, setImageModelForm] =
    useState<KnowledgeImageModelCreateRequest>(EMPTY_IMAGE_MODEL_FORM);

  const index = useQuery({
    queryKey: ["knowledge-index-page", category, pageOffset],
    queryFn: () =>
      listKnowledgeIndexPage(
        category ? category : undefined,
        pageOffset,
        INDEX_PAGE_SIZE,
      ),
  });
  const indexEntries = useMemo(
    () => index.data?.entries ?? [],
    [index.data?.entries],
  );

  const imageModelSettings = useQuery({
    queryKey: ["knowledge-image-model-settings"],
    queryFn: loadKnowledgeImageModelSettings,
  });

  useEffect(() => {
    const settings = imageModelSettings.data;
    if (!settings) return;
    setImageModelDraft(
      settings.selected_model_valid ? (settings.selected_model ?? null) : null,
    );
  }, [imageModelSettings.data]);

  const preview = useQuery({
    queryKey: [
      "knowledge-preview",
      selected?.index_id,
      selected ? entryPreviewPath(selected) : "",
      selected?.source_anchor,
    ],
    queryFn: () =>
      readKnowledgeFile(
        selected ? entryPreviewPath(selected) : "",
        selected?.source_anchor,
      ),
    enabled: Boolean(selected),
  });

  const categories = useMemo(() => {
    const set = new Set<string>(DEFAULT_CATEGORIES);
    for (const entry of indexEntries) {
      if (entry.category) set.add(entry.category);
    }
    return Array.from(set).sort();
  }, [indexEntries]);

  const visibleEntries = useMemo(
    () => searchResults?.map((hit) => hit.entry) ?? indexEntries,
    [indexEntries, searchResults],
  );

  const knowledgeTree = useMemo(() => {
    const typeMap = new Map<string, Map<string, KnowledgeIndexEntry[]>>();
    for (const entry of visibleEntries) {
      const type = entry.category?.trim()
        ? entry.category
        : entry.entry_type?.trim()
          ? entry.entry_type
          : "未分类";
      const path = entryFilePath(entry);
      if (!typeMap.has(type)) typeMap.set(type, new Map());
      const fileMap = typeMap.get(type);
      fileMap?.set(path, [...(fileMap.get(path) ?? []), entry]);
    }
    return Array.from(typeMap.entries())
      .sort(([left], [right]) => left.localeCompare(right, "zh-CN"))
      .map(([type, fileMap]) => ({
        type,
        files: Array.from(fileMap.entries())
          .sort(([left], [right]) =>
            fileName(left).localeCompare(fileName(right), "zh-CN"),
          )
          .map(([path, entries]) => ({
            path,
            entries: entries.sort((left, right) => {
              const leftIsChunk = isGeneratedChunk(left);
              const rightIsChunk = isGeneratedChunk(right);
              if (leftIsChunk !== rightIsChunk) return leftIsChunk ? 1 : -1;
              const orderDelta = chunkOrder(left) - chunkOrder(right);
              if (orderDelta !== 0) return orderDelta;
              return (left.title ?? "").localeCompare(
                right.title ?? "",
                "zh-CN",
              );
            }),
          })),
      }));
  }, [visibleEntries]);

  useEffect(() => {
    const firstEntry = visibleEntries[0];
    if (!firstEntry) return;
    if (!selected) {
      setSelected(firstEntry);
      return;
    }
    if (
      selected &&
      visibleEntries.length > 0 &&
      !visibleEntries.some((entry) => entry.index_id === selected.index_id)
    ) {
      setSelected(firstEntry);
    }
  }, [selected, visibleEntries]);

  useEffect(() => {
    if (knowledgeTree.length === 0) return;
    setExpandedTree((current) => {
      const next = new Set(current);
      const firstType = knowledgeTree[0];
      if (firstType) {
        next.add(`type:${firstType.type}`);
        const firstFile = firstType.files[0];
        if (firstFile) next.add(`file:${firstFile.path}`);
      }
      return next;
    });
  }, [knowledgeTree]);

  useEffect(() => {
    setPreviewMode("preview");
    setDraftContent("");
  }, [selected?.index_id]);

  useEffect(() => {
    if (typeof preview.data?.content === "string") {
      setDraftContent(preview.data.content);
    }
  }, [preview.data?.content]);

  useEffect(() => {
    if (query.trim()) return;
    setSearchResults(null);
    setLastSearchQuery("");
  }, [query]);

  const upload = useMutation({
    mutationFn: (files: File[]) => uploadKnowledgeFiles(files),
    onSuccess: async () => {
      setSelected(null);
      setSearchResults(null);
      setPageOffset(0);
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const rebuild = useMutation({
    mutationFn: () => buildKnowledgeIndex(),
    onSuccess: async (data) => {
      setSelected(null);
      setSearchResults(null);
      setPageOffset(0);
      if (
        data.warnings?.some((warning) =>
          /supports_vision|多模态模型|图片模型/.test(warning),
        )
      ) {
        setImageModelDialogOpen(true);
      }
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const processIncoming = useMutation({
    mutationFn: () => processIncomingAndBuildKnowledgeIndex(),
    onSuccess: async (data) => {
      setSelected(null);
      setSearchResults(null);
      setPageOffset(0);
      if (
        data.index_build.warnings?.some((warning) =>
          /supports_vision|多模态模型|图片模型/.test(warning),
        )
      ) {
        setImageModelDialogOpen(true);
      }
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const search = useMutation({
    mutationFn: ({ text }: { text: string }) =>
      searchKnowledgeIndex(text, category ? category : undefined, 50),
    onSuccess: (data, variables) => {
      setLastSearchQuery(variables.text);
      setSearchResults(data.results);
      setSelected(data.results[0]?.entry ?? null);
    },
  });

  const recallTest = useMutation({
    mutationFn: ({ text }: { text: string }) =>
      searchKnowledgeIndex(text, category ? category : undefined, 20),
    onSuccess: (_data, variables) => {
      setLastRecallQuery(variables.text);
    },
  });

  const recallEval = useMutation({
    mutationFn: () =>
      evaluateKnowledgeRecall(
        DEFAULT_RECALL_EVAL_CASES,
        category ? category : undefined,
        10,
      ),
  });

  const batchReview = useMutation({
    mutationFn: ({
      evidenceIds,
      verificationStatus,
    }: {
      evidenceIds: string[];
      verificationStatus: "human_verified" | "rejected";
    }) =>
      batchReviewKnowledgeEvidence(
        evidenceIds,
        verificationStatus,
        "default",
        verificationStatus === "human_verified"
          ? "在知识库列表中批量确认。"
          : "在知识库列表中批量标记为无关图片。",
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const saveImageModel = useMutation({
    mutationFn: (modelName: string) =>
      updateKnowledgeImageModelSettings(modelName),
    onSuccess: async (settings) => {
      setImageModelDraft(settings.selected_model ?? null);
      setImageModelDialogOpen(false);
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-image-model-settings"],
      });
    },
  });

  const createImageModel = useMutation({
    mutationFn: async () => {
      const modelName = imageModelForm.model_name.trim();
      const provider = imageModelForm.provider.trim();
      const result = await createKnowledgeImageModel({
        model_name: modelName,
        provider,
        url: optionalTrim(imageModelForm.url),
        api_key: optionalTrim(imageModelForm.api_key),
      });
      const createdModel = [...result.models]
        .reverse()
        .find(
          (model) =>
            model.supports_vision !== false &&
            model.provider === provider &&
            model.model === modelName,
        );
      if (!createdModel?.name) {
        throw new Error("视觉模型已保存，但无法确认其配置名称。");
      }
      return updateKnowledgeImageModelSettings(createdModel.name);
    },
    onSuccess: async (settings) => {
      setImageModelForm(EMPTY_IMAGE_MODEL_FORM);
      setImageModelDraft(settings.selected_model ?? null);
      setImageModelDialogOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["knowledge-image-model-settings"],
        }),
        queryClient.invalidateQueries({ queryKey: ["managed-models"] }),
        queryClient.invalidateQueries({ queryKey: ["models"] }),
      ]);
    },
  });

  const remove = useMutation({
    mutationFn: async (entry: KnowledgeIndexEntry) => {
      if (entry.evidence_id && entry.applicant_id) {
        await deleteKnowledgeEvidence(entry.evidence_id, entry.applicant_id);
        return;
      }
      await deleteKnowledgeFile(
        isGeneratedChunk(entry)
          ? entryPreviewPath(entry)
          : entryFilePath(entry),
        !isGeneratedChunk(entry),
      );
    },
    onSuccess: async () => {
      setSelected(null);
      setSearchResults(null);
      setPageOffset(0);
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const savePreview = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("请选择要保存的知识条目。");
      return saveKnowledgeFile(
        entryPreviewPath(selected),
        draftContent,
        isGeneratedChunk(selected) ? null : selected.source_anchor,
      );
    },
    onSuccess: async () => {
      setPreviewMode("preview");
      await queryClient.invalidateQueries({ queryKey: ["knowledge-preview"] });
      await queryClient.invalidateQueries({
        queryKey: ["knowledge-index-page"],
      });
    },
  });

  const buildStats = processIncoming.data?.index_build ?? rebuild.data;
  const running =
    upload.isPending || processIncoming.isPending || rebuild.isPending;
  const totalIndexEntries = index.data?.total ?? indexEntries.length;
  const progressWidth = running
    ? "68%"
    : buildStats
      ? "100%"
      : `${Math.min(100, Math.max(8, totalIndexEntries * 8))}%`;
  const parserSummary = buildStats?.parser_counts
    ? Object.entries(buildStats.parser_counts)
        .map(([name, count]) => `${name} ${count}`)
        .join(" / ")
    : "";
  const selectedTitle = selected
    ? selected.title?.trim()
      ? selected.title
      : fileName(selected.file_path)
    : "";
  const selectedPreviewPath = selected ? entryPreviewPath(selected) : "";
  const canEditPreview = Boolean(
    selected &&
    typeof preview.data?.content === "string" &&
    isEditableKnowledgePath(selectedPreviewPath),
  );
  const displayedPreviewContent =
    previewMode === "edit" ? draftContent : (preview.data?.content ?? "");
  const saveErrorMessage =
    savePreview.error instanceof Error
      ? savePreview.error.message
      : "保存失败，请稍后重试。";
  const searchErrorMessage =
    search.error instanceof Error
      ? search.error.message
      : "搜索失败，请稍后重试。";
  const recallErrorMessage =
    recallTest.error instanceof Error
      ? recallTest.error.message
      : "召回测试失败，请稍后重试。";
  const recallEvalErrorMessage =
    recallEval.error instanceof Error
      ? recallEval.error.message
      : "评测失败，请稍后重试。";
  const recallResults = useMemo(
    () => recallTest.data?.results ?? [],
    [recallTest.data?.results],
  );
  const recallMetrics = useMemo(() => {
    const totalEntries = totalIndexEntries;
    const totalFiles = new Set(indexEntries.map(entryFilePath)).size;
    const uniqueFiles = new Set(
      recallResults.map((hit) => entryFilePath(hit.entry)),
    ).size;
    const scores = recallResults.map((hit) => boundedSearchScore(hit.score));
    const maxScore = scores.length ? Math.max(...scores) : 0;
    const avgScore = scores.length
      ? scores.reduce((sum, score) => sum + score, 0) / scores.length
      : 0;
    const fields = new Set<string>();
    for (const hit of recallResults) {
      for (const field of hit.matched_fields ?? []) fields.add(field);
    }
    return {
      totalEntries,
      count: recallResults.length,
      fileCoverage: totalFiles
        ? Math.round((uniqueFiles / totalFiles) * 100)
        : 0,
      maxScore,
      avgScore,
      fields: Array.from(fields),
    };
  }, [indexEntries, recallResults, totalIndexEntries]);
  const recallEvalSummary = recallEval.data;
  const pageStart = totalIndexEntries === 0 ? 0 : pageOffset + 1;
  const pageEnd = Math.min(pageOffset + INDEX_PAGE_SIZE, totalIndexEntries);
  const canPageBack = pageOffset > 0;
  const canPageForward = pageOffset + INDEX_PAGE_SIZE < totalIndexEntries;
  const modelReviewedEvidence = visibleEntries.filter(
    (entry) =>
      Boolean(entry.evidence_id) &&
      entry.verification_status === "needs_review" &&
      entry.metadata?.extraction_status === "completed",
  );
  const confirmableEvidenceIds = modelReviewedEvidence
    .filter((entry) => entry.evidence_type !== "non_evidence_image")
    .map((entry) => entry.evidence_id)
    .filter((evidenceId): evidenceId is string => Boolean(evidenceId));
  const nonEvidenceIds = modelReviewedEvidence
    .filter((entry) => entry.evidence_type === "non_evidence_image")
    .map((entry) => entry.evidence_id)
    .filter((evidenceId): evidenceId is string => Boolean(evidenceId));
  const activeImageModel = imageModelSettings.data?.vision_models.find(
    (model) => model.name === imageModelSettings.data?.selected_model,
  );
  const imageModelStatus = imageModelSettings.isLoading
    ? "读取中"
    : imageModelSettings.isError
      ? "读取失败"
      : imageModelSettings.data?.selected_model_valid
        ? (activeImageModel?.display_name ?? activeImageModel?.name ?? "已配置")
        : "图片识别模型未配置";

  function toggleTreeKey(key: string) {
    setExpandedTree((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function runSearch() {
    const text = query.trim();
    if (!text) {
      setSearchResults(null);
      setLastSearchQuery("");
      return;
    }
    search.mutate({ text });
  }

  function runRecallTest() {
    const text = recallQuery.trim();
    if (!text) return;
    recallTest.mutate({ text });
  }

  return (
    <main className="codex-main single">
      <div className="kb-view">
        <div className="kb-container">
          <section className="kb-hero">
            <div>
              <h1>知识库管理</h1>
            </div>
            <button
              type="button"
              className={`kb-image-model-status ${imageModelSettings.data?.selected_model_valid ? "configured" : "warning"}`}
              aria-label={
                imageModelSettings.data?.selected_model_valid
                  ? `图片识别模型：${imageModelStatus}`
                  : "图片识别模型未配置"
              }
              aria-haspopup="dialog"
              aria-controls="knowledge-image-model-dialog"
              onClick={() => {
                setImageModelDraft(
                  imageModelSettings.data?.selected_model_valid
                    ? (imageModelSettings.data.selected_model ?? null)
                    : null,
                );
                setImageModelDialogOpen(true);
              }}
            >
              <span
                className={`kb-image-model-dot${imageModelSettings.data?.selected_model_valid ? "configured" : ""}`}
                aria-hidden="true"
              />
              <strong
                className="kb-image-model-label"
                title={`图片识别模型：${imageModelStatus}`}
              >
                {imageModelStatus}
              </strong>
              <Settings2Icon />
            </button>
          </section>

          <div className="kb-process">
            <article className="kb-card kb-ingest-card">
              <div className="kb-card-head">
                <div className="kb-card-icon">
                  <UploadIcon />
                </div>
                <div>
                  <div className="kb-card-title">上传政策与材料</div>
                </div>
              </div>
              <button
                type="button"
                className="dropzone"
                onClick={() => uploadRef.current?.click()}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  const files = Array.from(event.dataTransfer.files ?? []);
                  if (files.length) upload.mutate(files);
                }}
              >
                <UploadIcon />
                <span>
                  拖入文件或 <strong>点击上传</strong>
                </span>
              </button>
              {upload.isPending ? (
                <div className="upload-status-list">
                  <div className="upload-status-row pending">
                    <Loader2Icon className="spin" />
                    <span>正在上传文件...</span>
                  </div>
                </div>
              ) : upload.data?.files?.length ? (
                <div className="upload-status-list">
                  {upload.data.files.map((file) => (
                    <div
                      key={file.file_path}
                      className="upload-status-row done"
                    >
                      <FileTextIcon />
                      <span>
                        {file.original_filename?.trim()
                          ? file.original_filename
                          : file.filename}
                      </span>
                      <strong>
                        {file.evidence_id
                          ? file.deduplicated
                            ? "证据已存在"
                            : "已加入图片识别队列"
                          : "已上传"}
                      </strong>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="kb-ingest-actions">
                <button
                  type="button"
                  className="organize-btn"
                  onClick={() => processIncoming.mutate()}
                  disabled={processIncoming.isPending}
                >
                  {processIncoming.isPending ? (
                    <Loader2Icon className="spin" />
                  ) : (
                    <RefreshCwIcon />
                  )}
                  整理入库并构建索引
                </button>
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => rebuild.mutate()}
                  disabled={rebuild.isPending}
                >
                  {rebuild.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <RefreshCwIcon size={14} />
                  )}
                  仅重建索引
                </button>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: progressWidth }}
                />
              </div>
              <div className="progress-text">
                <span>
                  {running
                    ? "正在处理"
                    : buildStats
                      ? `已扫描 ${buildStats.scanned_files} 个文件`
                      : `${totalIndexEntries} 个索引条目`}
                </span>
                <span>
                  {buildStats
                    ? `新增 ${buildStats.created} / 更新 ${buildStats.updated} / 复用 ${buildStats.reused ?? 0}`
                    : `${processIncoming.data?.organization?.moved ?? 0} 个文件已整理`}
                </span>
              </div>
              {buildStats?.scale_stats ? (
                <div className="progress-text">
                  <span>
                    索引 {buildStats.scale_stats.index_entries_total ?? 0} 条 /
                    JSON {formatBytes(buildStats.scale_stats.index_json_bytes)}{" "}
                    / SQLite{" "}
                    {formatBytes(buildStats.scale_stats.sqlite_index_bytes)}
                  </span>
                  <span>
                    {parserSummary
                      ? `解析 ${parserSummary}`
                      : `耗时 ${buildStats.scale_stats.elapsed_seconds ?? 0}s`}
                  </span>
                </div>
              ) : null}
              {buildStats?.warnings?.length ? (
                <div className="upload-status-list">
                  {buildStats.warnings.slice(0, 3).map((warning) => (
                    <div key={warning} className="upload-status-row pending">
                      <FileTextIcon />
                      <span>{warning}</span>
                    </div>
                  ))}
                </div>
              ) : null}
              {buildStats?.parse_errors?.length ? (
                <div className="upload-status-list">
                  {buildStats.parse_errors.slice(0, 3).map((error) => (
                    <div
                      key={`${error.file_path ?? ""}:${error.error ?? ""}`}
                      className="upload-status-row pending"
                    >
                      <FileTextIcon />
                      <span>
                        {error.file_path ?? "未知文件"}：
                        {error.error ?? "解析失败"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </article>

            <article className="kb-card kb-recall-card">
              <div className="kb-card-head">
                <div className="kb-card-icon">
                  <BarChart3Icon />
                </div>
                <div>
                  <div className="kb-card-title">知识库召回测试</div>
                </div>
              </div>
              <form
                className="kb-recall-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  runRecallTest();
                }}
              >
                <div className="search-box">
                  <SearchIcon size={16} />
                  <input
                    value={recallQuery}
                    placeholder="输入测试问题或关键词"
                    onChange={(event) => setRecallQuery(event.target.value)}
                  />
                  <button
                    type="submit"
                    disabled={!recallQuery.trim() || recallTest.isPending}
                  >
                    {recallTest.isPending ? "测试中" : "测试"}
                  </button>
                </div>
              </form>
              <div className="kb-ingest-actions compact">
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => recallEval.mutate()}
                  disabled={recallEval.isPending}
                >
                  {recallEval.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <BarChart3Icon size={14} />
                  )}
                  运行评测集
                </button>
              </div>
              <div className="kb-recall-metrics">
                <div>
                  <span>召回条目</span>
                  <strong>{recallMetrics.count}</strong>
                  <small>/ {recallMetrics.totalEntries}</small>
                </div>
                <div>
                  <span>文件覆盖</span>
                  <strong>{recallMetrics.fileCoverage}%</strong>
                </div>
                <div>
                  <span>最高分</span>
                  <strong>{formatSearchScore(recallMetrics.maxScore)}</strong>
                </div>
                <div>
                  <span>平均分</span>
                  <strong>{formatSearchScore(recallMetrics.avgScore)}</strong>
                </div>
              </div>
              {lastRecallQuery ? (
                <div className="kb-recall-summary">
                  <span>{lastRecallQuery}</span>
                  <strong>
                    {recallMetrics.fields.length
                      ? recallMetrics.fields.join(" / ")
                      : "无字段命中"}
                  </strong>
                </div>
              ) : null}
              {recallEvalSummary ? (
                <div className="kb-recall-summary">
                  <span>
                    评测集 {recallEvalSummary.hit_count}/
                    {recallEvalSummary.total_cases}
                  </span>
                  <strong>
                    Recall@10 {(recallEvalSummary.recall_at_k * 100).toFixed(0)}
                    % / MRR {recallEvalSummary.mrr.toFixed(2)}
                  </strong>
                </div>
              ) : null}
              {recallTest.isError ? (
                <div className="kb-error">{recallErrorMessage}</div>
              ) : null}
              {recallEval.isError ? (
                <div className="kb-error">{recallEvalErrorMessage}</div>
              ) : null}
              <div className="kb-recall-results">
                {recallTest.isPending ? (
                  <div className="empty-state compact">正在测试召回</div>
                ) : recallResults.length ? (
                  recallResults.slice(0, 5).map((hit) => (
                    <button
                      key={hit.entry.index_id}
                      type="button"
                      onClick={() => setSelected(hit.entry)}
                    >
                      <span>
                        {hit.entry.title?.trim()
                          ? hit.entry.title
                          : fileName(hit.entry.file_path)}
                      </span>
                      <strong>{formatSearchScore(hit.score)}</strong>
                    </button>
                  ))
                ) : lastRecallQuery ? (
                  <div className="empty-state compact">未召回相关条目。</div>
                ) : null}
              </div>
            </article>
          </div>

          <section className="kb-tree-section">
            <h2>
              <FolderIcon />
              知识库预览
            </h2>

            <div className="kb-toolbar">
              <div className="search-box">
                <SearchIcon size={16} />
                <input
                  value={query}
                  placeholder="搜索政策、指标、申报章节或技术关键词"
                  onChange={(event) => setQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && query.trim()) runSearch();
                  }}
                />
                <button
                  type="button"
                  onClick={runSearch}
                  disabled={!query.trim() || search.isPending}
                >
                  {search.isPending ? "搜索中" : "搜索"}
                </button>
              </div>
              <select
                value={category}
                onChange={(event) => {
                  setCategory(event.target.value);
                  setPageOffset(0);
                  setSearchResults(null);
                  setLastSearchQuery("");
                  setLastRecallQuery("");
                  recallTest.reset();
                  setSelected(null);
                }}
              >
                <option value="">全部分类</option>
                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              {searchResults ? (
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => {
                    setSearchResults(null);
                    setLastSearchQuery("");
                  }}
                >
                  清除搜索
                </button>
              ) : null}
              {confirmableEvidenceIds.length ? (
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={batchReview.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `确认将当前列表中 ${confirmableEvidenceIds.length} 项已识别证据标记为人工确认？字段不完整的证据会自动跳过。`,
                      )
                    ) {
                      batchReview.mutate({
                        evidenceIds: confirmableEvidenceIds,
                        verificationStatus: "human_verified",
                      });
                    }
                  }}
                >
                  {batchReview.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <SaveIcon size={14} />
                  )}
                  批量确认证据 ({confirmableEvidenceIds.length})
                </button>
              ) : null}
              {nonEvidenceIds.length ? (
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={batchReview.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `确认将当前列表中 ${nonEvidenceIds.length} 项模型判断的非证据图片标记为无关？`,
                      )
                    ) {
                      batchReview.mutate({
                        evidenceIds: nonEvidenceIds,
                        verificationStatus: "rejected",
                      });
                    }
                  }}
                >
                  <Trash2Icon size={14} />
                  标记无关图片 ({nonEvidenceIds.length})
                </button>
              ) : null}
            </div>
            {batchReview.data ? (
              <div className="kb-batch-review-result">
                已更新 {batchReview.data.updated.length} 项
                {Object.keys(batchReview.data.skipped).length
                  ? `，跳过 ${Object.keys(batchReview.data.skipped).length} 项（字段不足或已不存在）`
                  : ""}
              </div>
            ) : null}
            {batchReview.isError ? (
              <div className="kb-error">
                {batchReview.error instanceof Error
                  ? batchReview.error.message
                  : "批量审核失败，请稍后重试。"}
              </div>
            ) : null}
            {!searchResults ? (
              <div className="kb-search-result-line">
                <FolderIcon size={14} />
                <span>
                  {pageStart}-{pageEnd}
                </span>
                <strong>共 {totalIndexEntries} 条</strong>
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={!canPageBack || index.isFetching}
                  onClick={() =>
                    setPageOffset(Math.max(0, pageOffset - INDEX_PAGE_SIZE))
                  }
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={!canPageForward || index.isFetching}
                  onClick={() => setPageOffset(pageOffset + INDEX_PAGE_SIZE)}
                >
                  下一页
                </button>
              </div>
            ) : null}
            {searchResults ? (
              <div className="kb-search-result-line">
                <SearchIcon size={14} />
                <span>{lastSearchQuery}</span>
                <strong>{searchResults.length} 个结果</strong>
              </div>
            ) : null}
            {search.isError ? (
              <div className="kb-error">{searchErrorMessage}</div>
            ) : null}

            <div className="kb-tree-grid">
              <div className="kb-tree">
                {index.isLoading ? (
                  <div className="empty-state compact">正在加载知识索引</div>
                ) : visibleEntries.length === 0 ? (
                  <div className="empty-state compact">
                    暂无知识条目。先上传文件并构建索引。
                  </div>
                ) : (
                  knowledgeTree.map((group) => {
                    const typeKey = `type:${group.type}`;
                    const typeOpen = expandedTree.has(typeKey);
                    return (
                      <div key={group.type} className="tree-node">
                        <button
                          type="button"
                          className="tree-row folder"
                          onClick={() => toggleTreeKey(typeKey)}
                        >
                          {typeOpen ? (
                            <ChevronDownIcon className="chev" />
                          ) : (
                            <ChevronRightIcon className="chev" />
                          )}
                          <FolderIcon className="ficon folder" />
                          <span className="fname">{group.type}</span>
                          <span className="fsize">{group.files.length}</span>
                        </button>
                        <div
                          className={`tree-children${typeOpen ? "open" : ""}`}
                        >
                          {group.files.map((file) => {
                            const fileKey = `file:${file.path}`;
                            const fileOpen = expandedTree.has(fileKey);
                            const activeFile = file.entries.some(
                              (entry) => entry.index_id === selected?.index_id,
                            );
                            const firstEntry = file.entries[0];
                            return (
                              <div key={file.path} className="tree-node">
                                <button
                                  type="button"
                                  className={`tree-row file-folder${activeFile ? "active" : ""}`}
                                  onClick={() => {
                                    if (firstEntry) setSelected(firstEntry);
                                    toggleTreeKey(fileKey);
                                  }}
                                >
                                  {fileOpen ? (
                                    <ChevronDownIcon className="chev" />
                                  ) : (
                                    <ChevronRightIcon className="chev" />
                                  )}
                                  <FileTextIcon className="ficon file" />
                                  <span className="fname">
                                    {entryFileTitle(
                                      firstEntry ??
                                        ({
                                          file_path: file.path,
                                          title: fileName(file.path),
                                          index_id: file.path,
                                        } as KnowledgeIndexEntry),
                                    )}
                                  </span>
                                  <span className="fsize">
                                    {file.entries.length}
                                  </span>
                                </button>
                                <div
                                  className={`tree-children${fileOpen ? "open" : ""}`}
                                >
                                  {file.entries.map((entry) => (
                                    <button
                                      key={entry.index_id}
                                      type="button"
                                      className={`tree-row chunk-row${selected?.index_id === entry.index_id ? "active" : ""}`}
                                      onClick={() => setSelected(entry)}
                                    >
                                      <span className="tree-indent" />
                                      <FileTextIcon className="ficon file" />
                                      <span className="fname">
                                        {entry.title?.trim()
                                          ? entry.title
                                          : fileName(entry.file_path)}
                                      </span>
                                      <span className="fsize">
                                        {isGeneratedChunk(entry)
                                          ? entryContentKind(entry)
                                          : (entry.entry_type ?? "源文件")}
                                      </span>
                                    </button>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>

              <div className="kb-chunk-preview">
                {selected ? (
                  <>
                    <div className="kb-preview-head">
                      <div className="chunk-meta">
                        <span className="chunk-tag">
                          {selected.category?.trim()
                            ? selected.category
                            : "未分类"}
                        </span>
                        {selected.domain ? (
                          <span className="chunk-tag muted">
                            {selected.domain}
                          </span>
                        ) : null}
                        {typeof selected.confidence === "number" ? (
                          <span className="chunk-tag muted">
                            置信度 {Math.round(selected.confidence * 100)}%
                          </span>
                        ) : null}
                        <span className="chunk-tag muted">
                          {formatDateTime(selected.updated_at)}
                        </span>
                      </div>
                      <div className="kb-preview-mode-actions">
                        <button
                          type="button"
                          className={previewMode === "preview" ? "active" : ""}
                          aria-label="Markdown 预览"
                          title="Markdown 预览"
                          onClick={() => setPreviewMode("preview")}
                        >
                          <EyeIcon size={14} />
                        </button>
                        <button
                          type="button"
                          className={previewMode === "edit" ? "active" : ""}
                          aria-label="编辑"
                          title="编辑"
                          onClick={() => setPreviewMode("edit")}
                          disabled={!canEditPreview}
                        >
                          <PencilIcon size={14} />
                        </button>
                        {previewMode === "edit" ? (
                          <>
                            <button
                              type="button"
                              aria-label="保存"
                              title="保存"
                              onClick={() => savePreview.mutate()}
                              disabled={
                                !canEditPreview || savePreview.isPending
                              }
                            >
                              {savePreview.isPending ? (
                                <Loader2Icon size={14} className="spin" />
                              ) : (
                                <SaveIcon size={14} />
                              )}
                            </button>
                            <button
                              type="button"
                              aria-label="还原"
                              title="还原"
                              onClick={() =>
                                setDraftContent(preview.data?.content ?? "")
                              }
                              disabled={savePreview.isPending}
                            >
                              <RefreshCwIcon size={14} />
                            </button>
                          </>
                        ) : null}
                      </div>
                    </div>
                    <div className="chunk-title">{selectedTitle}</div>
                    <p className="kb-summary">
                      {selected.summary?.trim()
                        ? selected.summary
                        : "该条目暂无摘要。"}
                    </p>
                    <div className="kb-tags">
                      {(selected.keywords ?? selected.technical_terms ?? [])
                        .slice(0, 12)
                        .map((tag) => (
                          <span key={tag}>{tag}</span>
                        ))}
                    </div>
                    <div className="fp-actions">
                      <button
                        type="button"
                        onClick={async () => {
                          const sourcePath = entryFilePath(selected);
                          downloadBlob(
                            await downloadKnowledgeFile(sourcePath),
                            fileName(sourcePath),
                          );
                        }}
                      >
                        <DownloadIcon size={14} />
                        下载源文件
                      </button>
                      <button
                        type="button"
                        onClick={() => remove.mutate(selected)}
                        disabled={remove.isPending}
                      >
                        <Trash2Icon size={14} />
                        删除
                      </button>
                    </div>
                    <div className="chunk-text">
                      {preview.isLoading ? (
                        <div className="empty-state compact">正在读取内容</div>
                      ) : preview.data?.content ? (
                        previewMode === "edit" ? (
                          <textarea
                            className="knowledge-markdown-editor"
                            value={draftContent}
                            onChange={(event) =>
                              setDraftContent(event.target.value)
                            }
                          />
                        ) : (
                          <div className="msg-content kb-markdown-view">
                            <MarkdownRenderer
                              content={displayedPreviewContent}
                            />
                          </div>
                        )
                      ) : (
                        <span>选择条目后会展示文件片段或摘要。</span>
                      )}
                    </div>
                    {savePreview.isError ? (
                      <div className="kb-error">{saveErrorMessage}</div>
                    ) : null}
                  </>
                ) : (
                  <div className="empty-state compact">
                    <FolderIcon size={22} />
                    请选择一个知识条目预览。
                  </div>
                )}
              </div>
            </div>
          </section>
        </div>
      </div>

      <input
        ref={uploadRef}
        type="file"
        multiple
        accept=".md,.markdown,.txt,.docx,.pdf,.xlsx,.xls,.csv,.tsv,.jpg,.jpeg,.png,.webp,.tif,.tiff"
        hidden
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length) upload.mutate(files);
          event.currentTarget.value = "";
        }}
      />
      {imageModelDialogOpen ? (
        <div
          className="modal-backdrop knowledge-image-model-backdrop"
          role="presentation"
          onMouseDown={() => setImageModelDialogOpen(false)}
        >
          <div
            id="knowledge-image-model-dialog"
            className="knowledge-image-model-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="knowledge-image-model-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <div>
                <h2 id="knowledge-image-model-title">知识库图片识别模型</h2>
                <p>仅显示已声明支持图像输入的模型，保存后立即生效。</p>
              </div>
              <button
                type="button"
                className="icon-btn"
                aria-label="关闭"
                onClick={() => setImageModelDialogOpen(false)}
              >
                <XIcon size={16} />
              </button>
            </div>

            <div className="knowledge-image-model-list">
              {imageModelSettings.isLoading ? (
                <div className="empty-state compact">
                  <Loader2Icon className="spin" />
                  正在读取模型配置
                </div>
              ) : imageModelSettings.isError ? (
                <div className="kb-error">
                  {imageModelSettings.error instanceof Error
                    ? imageModelSettings.error.message
                    : "读取模型配置失败。"}
                </div>
              ) : imageModelSettings.data?.vision_models.length ? (
                imageModelSettings.data.vision_models.map((model) => (
                  <label
                    key={model.name}
                    className={`knowledge-image-model-option${imageModelDraft === model.name ? "selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name="knowledge-image-model"
                      value={model.name}
                      checked={imageModelDraft === model.name}
                      onChange={() => setImageModelDraft(model.name)}
                    />
                    <span>
                      <strong>
                        {preferredText(model.display_name, model.name)}
                      </strong>
                      <small>
                        {preferredText(model.provider, "custom")} ·{" "}
                        {preferredText(model.model, model.name)}
                      </small>
                    </span>
                    <em>支持视觉</em>
                  </label>
                ))
              ) : (
                <div className="empty-state compact">
                  <ImageIcon size={24} />
                  图片识别模型未配置，请在下方新增视觉模型。
                </div>
              )}
            </div>

            <div className="knowledge-image-model-create">
              <div className="knowledge-image-model-create-head">
                <h3>新增视觉模型</h3>
                <p>
                  配置项与“设置 →
                  模型供应商”一致；保存后将自动启用视觉能力并用于知识库。
                </p>
              </div>
              <div className="form-grid add-model-form knowledge-image-model-form">
                <select
                  aria-label="模型供应商"
                  value={imageModelForm.provider}
                  onChange={(event) => {
                    const provider = modelProviderOptions.find(
                      (item) => item.value === event.target.value,
                    );
                    setImageModelForm((form) => ({
                      ...form,
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
                  value={imageModelForm.model_name}
                  onChange={(event) =>
                    setImageModelForm((form) => ({
                      ...form,
                      model_name: event.target.value,
                    }))
                  }
                />
                <input
                  placeholder="URL"
                  value={imageModelForm.url ?? ""}
                  onChange={(event) =>
                    setImageModelForm((form) => ({
                      ...form,
                      url: event.target.value,
                    }))
                  }
                />
                <input
                  placeholder="API Key"
                  type="password"
                  autoComplete="new-password"
                  value={imageModelForm.api_key ?? ""}
                  onChange={(event) =>
                    setImageModelForm((form) => ({
                      ...form,
                      api_key: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="add-model-actions">
                <button
                  type="button"
                  className="primary-btn"
                  disabled={
                    !imageModelForm.model_name.trim() ||
                    !imageModelForm.provider.trim() ||
                    createImageModel.isPending
                  }
                  onClick={() => createImageModel.mutate()}
                >
                  {createImageModel.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <SaveIcon size={14} />
                  )}
                  保存并使用
                </button>
              </div>
              {createImageModel.isError ? (
                <div className="kb-error knowledge-image-model-error">
                  {createImageModel.error instanceof Error
                    ? createImageModel.error.message
                    : "新增视觉模型失败。"}
                </div>
              ) : null}
            </div>

            <div className="knowledge-image-model-foot">
              <span>图片识别不可用时，普通文档仍会继续构建知识索引。</span>
              <div>
                <button
                  type="button"
                  className="ghost-btn"
                  onClick={() => setImageModelDialogOpen(false)}
                >
                  取消
                </button>
                <button
                  type="button"
                  className="primary-btn"
                  disabled={!imageModelDraft || saveImageModel.isPending}
                  onClick={() => {
                    if (imageModelDraft) saveImageModel.mutate(imageModelDraft);
                  }}
                >
                  {saveImageModel.isPending ? (
                    <Loader2Icon size={14} className="spin" />
                  ) : (
                    <SaveIcon size={14} />
                  )}
                  使用所选模型
                </button>
              </div>
            </div>
            {saveImageModel.isError ? (
              <div className="kb-error knowledge-image-model-error">
                {saveImageModel.error instanceof Error
                  ? saveImageModel.error.message
                  : "保存图片识别模型失败。"}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
