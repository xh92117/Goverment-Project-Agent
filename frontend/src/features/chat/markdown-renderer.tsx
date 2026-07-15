"use client";

import { Component, type MouseEvent, type ReactNode, useRef } from "react";
import { Streamdown } from "streamdown";

import { writeClipboardText } from "@/shared/lib/clipboard";

type MarkdownRendererProps = {
  content: string;
  isStreaming?: boolean;
  onCopied?: () => void;
};

type MarkdownRenderErrorBoundaryProps = {
  content: string;
  children: ReactNode;
};

type MarkdownRenderErrorBoundaryState = {
  hasError: boolean;
};

class MarkdownRenderErrorBoundary extends Component<
  MarkdownRenderErrorBoundaryProps,
  MarkdownRenderErrorBoundaryState
> {
  state: MarkdownRenderErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): MarkdownRenderErrorBoundaryState {
    return { hasError: true };
  }

  componentDidUpdate(previousProps: MarkdownRenderErrorBoundaryProps) {
    if (previousProps.content !== this.props.content && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return <pre className="markdown-fallback">{this.props.content}</pre>;
    }
    return this.props.children;
  }
}

function findNearestTable(button: HTMLButtonElement, root: HTMLElement) {
  let current: HTMLElement | null = button;
  while (current && current !== root) {
    const table = current.querySelector("table");
    if (table instanceof HTMLTableElement) return table;
    current = current.parentElement;
  }
  return null;
}

function isLikelyCopyButton(button: HTMLButtonElement) {
  const label = `${button.title ?? ""} ${button.getAttribute("aria-label") ?? ""}`.toLowerCase();
  if (label.includes("copy") || label.includes("复制")) return true;
  const siblings = button.parentElement ? Array.from(button.parentElement.querySelectorAll("button")) : [];
  return siblings.length > 1 && siblings[0] === button;
}

function tableToMarkdown(table: HTMLTableElement) {
  const rows = Array.from(table.rows).map((row) =>
    Array.from(row.cells).map((cell) => cell.textContent?.replace(/\s+/g, " ").trim() ?? ""),
  );
  if (!rows.length) return "";
  const head = rows[0] ?? [];
  const body = rows.slice(1);
  const separator = head.map(() => "---");
  return [head, separator, ...body].map((row) => `| ${row.join(" | ")} |`).join("\n");
}

export function MarkdownRenderer({ content, isStreaming = false, onCopied }: MarkdownRendererProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  function handleClickCapture(event: MouseEvent<HTMLDivElement>) {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("button");
    const root = rootRef.current;
    if (!(button instanceof HTMLButtonElement) || !root?.contains(button)) return;
    if (!isLikelyCopyButton(button)) return;

    const table = findNearestTable(button, root);
    if (!table) return;

    event.preventDefault();
    event.stopPropagation();
    const tableMarkdown = tableToMarkdown(table);
    if (!tableMarkdown) return;
    onCopied?.();
    void writeClipboardText(tableMarkdown).catch(() => undefined);
  }

  return (
    <MarkdownRenderErrorBoundary content={content}>
      <div ref={rootRef} className="markdown-renderer" onClickCapture={handleClickCapture}>
        <Streamdown
          className="markdown-stream"
          controls={!isStreaming}
          isAnimating={isStreaming}
          parseIncompleteMarkdown
        >
          {content}
        </Streamdown>
      </div>
      {isStreaming ? <span aria-hidden="true" className="stream-cursor" /> : null}
    </MarkdownRenderErrorBoundary>
  );
}
