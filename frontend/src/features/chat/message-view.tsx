"use client";

import {
  CheckCircle2Icon,
  CopyIcon,
  Loader2Icon,
  RefreshCwIcon,
  Trash2Icon,
  TriangleAlertIcon,
  WrenchIcon,
} from "lucide-react";
import { useEffect, useState, type RefObject } from "react";

import type { StreamAction } from "@/features/chat/api";
import { MarkdownRenderer } from "@/features/chat/markdown-renderer";
import { buildTurns } from "@/features/chat/message-turns";
import {
  prepareAssistantContent,
  stripEmoji,
} from "@/features/chat/message-utils";
import type { LocalMessage } from "@/features/chat/message-utils";
import type { AssistantCitation } from "@/features/chat/message-utils";
import { writeClipboardText } from "@/shared/lib/clipboard";

function copyText(content: string, onCopied?: () => void) {
  onCopied?.();
  void writeClipboardText(content).catch(() => undefined);
}

function UserMessage({
  message,
  onCopied,
  onDelete,
  onRegenerate,
}: {
  message: LocalMessage;
  onCopied?: () => void;
  onDelete?: () => void;
  onRegenerate?: () => void;
}) {
  return (
    <div className="msg user">
      <div className="msg-avatar">我</div>
      <div className="msg-body">
        <div className="msg-content">
          <p>{message.content}</p>
        </div>
        <div className="user-message-actions" aria-label="用户消息操作">
          <button type="button" title="复制消息" onClick={() => copyText(message.content, onCopied)}>
            <CopyIcon />
            复制
          </button>
          <button type="button" title="删除本轮消息" disabled={!onDelete} onClick={onDelete}>
            <Trash2Icon />
            删除
          </button>
          <button type="button" title="重新生成回答" disabled={!onRegenerate} onClick={onRegenerate}>
            <RefreshCwIcon />
            重新生成
          </button>
        </div>
      </div>
    </div>
  );
}

function StreamActionIcon({ action }: { action: StreamAction }) {
  if (action.status === "completed") return <CheckCircle2Icon size={14} />;
  if (action.status === "error") return <TriangleAlertIcon size={14} />;
  if (action.status === "running") return <Loader2Icon size={14} />;
  return <WrenchIcon size={14} />;
}

function streamActionSummary(actions: StreamAction[]) {
  const running = actions.filter((action) => action.status === "running").length;
  const errors = actions.filter((action) => action.status === "error").length;
  if (running) return `${running} 个进行中`;
  if (errors) return `${errors} 个失败`;
  return "已完成";
}

function StreamActionList({
  actions,
  isStreaming,
}: {
  actions: StreamAction[];
  isStreaming?: boolean;
}) {
  const hasRunningAction = actions.some((action) => action.status === "running");
  const shouldForceOpen = isStreaming === true || hasRunningAction;
  const [open, setOpen] = useState(shouldForceOpen);

  useEffect(() => {
    setOpen(shouldForceOpen);
  }, [shouldForceOpen]);

  return (
    <details
      className="stream-action-panel"
      open={open}
      onToggle={(event) => setOpen(shouldForceOpen ? true : event.currentTarget.open)}
    >
      <summary>
        <span className="stream-action-summary-main">
          <WrenchIcon size={14} />
          工具调用过程
        </span>
        <span className="stream-action-summary-meta">
          {actions.length} 项 · {streamActionSummary(actions)}
        </span>
      </summary>
      <div className="stream-action-list" aria-label="运行步骤">
        {actions.map((action) => (
          <div key={action.id} className={`stream-action ${action.status}`}>
            <span className="stream-action-icon">
              <StreamActionIcon action={action} />
            </span>
            <span className="stream-action-text">
              <span className="stream-action-title">{action.title}</span>
              {action.detail ? <span className="stream-action-detail">{action.detail}</span> : null}
            </span>
          </div>
        ))}
      </div>
    </details>
  );
}

function CitationList({ citations }: { citations: AssistantCitation[] }) {
  if (!citations.length) return null;
  return (
    <div className="citation-list">
      <div className="citation-list-title">来源</div>
      <div className="citation-items">
        {citations.map((citation, index) => (
          <div
            key={`${citation.kind}-${citation.title}-${index}`}
            className={`citation-item ${citation.kind}`}
          >
            <span className="citation-kind">{citation.kind === "knowledge" ? "知识库" : "网页"}</span>
            <span className="citation-main">
              {citation.href ? (
                <a href={citation.href} target="_blank" rel="noreferrer">
                  {citation.title}
                </a>
              ) : (
                citation.title
              )}
              {citation.detail ? <span className="citation-detail">{citation.detail}</span> : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  userPrompt,
  assistantIds,
  isStreaming,
  onRegenerate,
  onCopied,
}: {
  message: LocalMessage;
  userPrompt?: string;
  assistantIds: string[];
  isStreaming?: boolean;
  onRegenerate?: (prompt: string, assistantIds: string[]) => void;
  onCopied?: () => void;
}) {
  const assistant = prepareAssistantContent(stripEmoji(message.content));
  const canRegenerate = Boolean(userPrompt && onRegenerate);
  const actionPanel = message.actions?.length ? (
    <StreamActionList actions={message.actions} isStreaming={isStreaming} />
  ) : null;

  return (
    <div className={`msg ai${isStreaming ? " streaming" : ""}`}>
      <div className="msg-avatar">策</div>
      <div className="msg-body">
        <div className="answer-box">
          <div className="answer-head">
            <div className="msg-name">智策助手</div>
            <div className="answer-actions">
              <button type="button" title="复制回答" onClick={() => copyText(message.content, onCopied)}>
                <CopyIcon />
              </button>
              <button
                type="button"
                title="重新生成"
                disabled={!canRegenerate}
                onClick={() => {
                  if (userPrompt) onRegenerate?.(userPrompt, assistantIds);
                }}
              >
                <RefreshCwIcon />
              </button>
            </div>
          </div>
          {isStreaming ? actionPanel : null}
          <div className="msg-content">
            {assistant.content ? (
              <MarkdownRenderer content={assistant.content} isStreaming={isStreaming} onCopied={onCopied} />
            ) : (
              <span className="stream-placeholder">
                {isStreaming ? "正在生成回答..." : "本次运行未生成最终回答。可以发送“继续”，或点击重新生成、缩小问题范围后重试。"}
              </span>
            )}
          </div>
          <CitationList citations={assistant.citations} />
          {!isStreaming ? actionPanel : null}
        </div>
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  endRef,
  isRunning = false,
  onRegenerate,
  onDeleteMessages,
}: {
  messages: LocalMessage[];
  endRef?: RefObject<HTMLDivElement | null>;
  isRunning?: boolean;
  onRegenerate?: (prompt: string, assistantIds: string[]) => void;
  onDeleteMessages?: (messageIds: string[]) => void;
}) {
  const turns = buildTurns(messages);
  const [copyToastVisible, setCopyToastVisible] = useState(false);
  const [copyToastTick, setCopyToastTick] = useState(0);

  function showCopiedToast() {
    setCopyToastVisible(true);
    setCopyToastTick((tick) => tick + 1);
  }

  useEffect(() => {
    if (!copyToastVisible) return undefined;
    const handle = window.setTimeout(() => setCopyToastVisible(false), 1300);
    return () => window.clearTimeout(handle);
  }, [copyToastVisible, copyToastTick]);

  return (
    <div className="messages">
      {turns.map((turn, index) => (
        <div key={turn.id} className="message-turn">
          {turn.user ? (
            <UserMessage
              message={turn.user}
              onCopied={showCopiedToast}
              onDelete={
                onDeleteMessages ? () => onDeleteMessages([turn.user!.id, ...turn.assistantIds]) : undefined
              }
              onRegenerate={
                onRegenerate && !isRunning
                  ? () => onRegenerate(turn.user!.content, turn.assistantIds)
                  : undefined
              }
            />
          ) : null}
          {turn.assistant ? (
            <AssistantMessage
              message={turn.assistant}
              userPrompt={turn.user?.content}
              assistantIds={turn.assistantIds}
              isStreaming={isRunning && index === turns.length - 1}
              onRegenerate={onRegenerate}
              onCopied={showCopiedToast}
            />
          ) : null}
        </div>
      ))}
      {copyToastVisible ? (
        <div className="copy-toast" role="status" aria-live="polite">
          已复制
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  );
}
