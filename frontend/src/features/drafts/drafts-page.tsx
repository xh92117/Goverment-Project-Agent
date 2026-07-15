"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DownloadIcon,
  FileTextIcon,
  HistoryIcon,
  Loader2Icon,
  SaveIcon,
  Trash2Icon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  createDraftVersion,
  deleteDraft,
  downloadDraft,
  listDrafts,
  readDraft,
  saveDraft,
} from "@/features/drafts/api";
import type { DraftDownloadFormat, ProposalDraftFile } from "@/features/drafts/api";
import { formatDateTime } from "@/shared/lib/format";

function draftKey(file: ProposalDraftFile) {
  return `${file.task_name}/${file.section_name}`;
}

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

export function DraftsPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<ProposalDraftFile | null>(null);
  const [content, setContent] = useState("");

  const drafts = useQuery({ queryKey: ["drafts"], queryFn: listDrafts });

  const flatDrafts = useMemo(() => drafts.data?.files ?? [], [drafts.data]);

  useEffect(() => {
    if (!selected && flatDrafts[0]) setSelected(flatDrafts[0]);
  }, [flatDrafts, selected]);

  const draftContent = useQuery({
    queryKey: ["draft-content", selected?.task_name, selected?.section_name],
    queryFn: () => readDraft(selected?.task_name ?? "", selected?.section_name ?? ""),
    enabled: Boolean(selected),
  });

  useEffect(() => {
    if (draftContent.data) setContent(draftContent.data.content);
  }, [draftContent.data]);

  const save = useMutation({
    mutationFn: () => saveDraft(selected?.task_name ?? "", selected?.section_name ?? "", content),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: ["drafts"] }),
  });

  const version = useMutation({
    mutationFn: () => createDraftVersion(selected?.task_name ?? "", selected?.section_name ?? ""),
  });

  const remove = useMutation({
    mutationFn: () => deleteDraft(selected?.task_name ?? "", selected?.section_name ?? ""),
    onSuccess: async () => {
      setSelected(null);
      setContent("");
      await queryClient.invalidateQueries({ queryKey: ["drafts"] });
    },
  });

  async function download(format: DraftDownloadFormat) {
    if (!selected) return;
    const blob = await downloadDraft(selected.task_name, selected.section_name, format);
    downloadBlob(blob, `${selected.section_name}.${format === "word" ? "docx" : "md"}`);
  }

  return (
    <main className="codex-main single">
      <header className="main-head">
        <div>
          <div className="mh-title">草稿</div>
          <div className="mh-breadcrumb">申报书章节、版本与导出</div>
        </div>
        <div className="mh-right">
          <span className="tag muted">{flatDrafts.length} 个章节</span>
        </div>
      </header>

      <div className="drafts-view">
        <aside className="draft-list">
          {drafts.isLoading ? (
            <div className="empty-state compact">正在加载草稿</div>
          ) : flatDrafts.length === 0 ? (
            <div className="empty-state compact">暂无草稿。可在项目对话中生成申报书章节。</div>
          ) : (
            flatDrafts.map((file) => (
              <button
                key={draftKey(file)}
                type="button"
                className={`draft-row${draftKey(selected ?? file) === draftKey(file) ? " active" : ""}`}
                onClick={() => setSelected(file)}
              >
                <FileTextIcon size={15} />
                <span>
                  <strong>{file.section_name}</strong>
                  <small>{file.task_name} · {formatDateTime(file.updated_at)}</small>
                </span>
              </button>
            ))
          )}
        </aside>

        <section className="draft-editor">
          {selected ? (
            <>
              <div className="editor-head">
                <div>
                  <h2>{selected.section_name}</h2>
                  <p>{selected.task_name}</p>
                </div>
                <div className="editor-actions">
                  <button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
                    {save.isPending ? <Loader2Icon size={14} className="spin" /> : <SaveIcon size={14} />}
                    保存
                  </button>
                  <button type="button" onClick={() => version.mutate()} disabled={version.isPending}>
                    <HistoryIcon size={14} />
                    建版本
                  </button>
                  <button type="button" onClick={() => download("markdown")}>
                    <DownloadIcon size={14} />
                    MD
                  </button>
                  <button type="button" onClick={() => download("word")}>
                    <DownloadIcon size={14} />
                    Word
                  </button>
                  <button type="button" onClick={() => remove.mutate()} disabled={remove.isPending}>
                    <Trash2Icon size={14} />
                    删除
                  </button>
                </div>
              </div>
              <textarea
                className="markdown-editor"
                value={content}
                onChange={(event) => setContent(event.target.value)}
                placeholder="选择草稿章节后编辑内容"
              />
            </>
          ) : (
            <div className="empty-state">请选择一个草稿章节。</div>
          )}
        </section>
      </div>
    </main>
  );
}
