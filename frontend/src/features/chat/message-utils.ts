import { isRawKnowledgePayload } from "@/features/chat/api";
import type { ChatMessage, StreamAction } from "@/features/chat/api";

export type LocalMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions?: StreamAction[];
};

export type AssistantCitation = {
  kind: "knowledge" | "web";
  title: string;
  detail?: string;
  href?: string;
};

const emojiPattern = /[\p{Extended_Pictographic}\uFE0F\u200D]/gu;
const knowledgeCitationPattern = /【知识库：([^】]+)】/g;
const webCitationPattern = /\[citation:([^\]]+)\]\(([^)]+)\)/g;
const bareCitationPattern = /\[citation:([^\]]+)\]/g;

function contentToText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((block) => {
        if (typeof block === "string") return block;
        if (block && typeof block === "object") {
          const record = block as Record<string, unknown>;
          if (typeof record.text === "string") return record.text;
          if (typeof record.content === "string") return record.content;
        }
        return "";
      })
      .join("");
  }
  return "";
}

function normalizeMessageItem(item: ChatMessage, index: number): LocalMessage | null {
  const nested =
    item.content && typeof item.content === "object" && !Array.isArray(item.content)
      ? (item.content as Record<string, unknown>)
      : null;
  const rawRole =
    item.role ??
    item.type ??
    (typeof nested?.role === "string" ? nested.role : undefined) ??
    (typeof nested?.type === "string" ? nested.type : undefined);
  const roleText = typeof rawRole === "string" ? rawRole.toLowerCase() : "";
  if (roleText.includes("tool") || item.event_type === "llm.tool.result") return null;
  const role = roleText === "user" || roleText === "human" ? "user" : "assistant";
  const rawContent = nested && "content" in nested ? nested.content : item.content;
  const content = contentToText(rawContent);
  if (!content) return null;
  if (role === "assistant" && isRawKnowledgePayload(content)) return null;
  const id =
    item.id ??
    (typeof nested?.id === "string" ? nested.id : undefined) ??
    (typeof item.seq === "number" ? `seq-${item.seq}` : `m-${index}`);
  return { id, role, content };
}

export function normalizeMessages(data: { messages?: ChatMessage[] } | ChatMessage[] | undefined) {
  const raw = Array.isArray(data) ? data : data?.messages ?? [];
  return raw.map(normalizeMessageItem).filter((item): item is LocalMessage => Boolean(item));
}

export function stripEmoji(content: string) {
  return content.replace(emojiPattern, "").replace(/[ \t]{2,}/g, " ").trim();
}

function normalizeOutsideFencedCode(content: string, normalize: (value: string) => string) {
  const lines = content.replace(/\r\n?/g, "\n").match(/[^\n]*\n|[^\n]+/g) ?? [];
  let output = "";
  let prose = "";
  let inFence = false;
  let fenceChar = "";
  let fenceLength = 0;

  const flushProse = () => {
    if (!prose) return;
    output += normalize(prose);
    prose = "";
  };

  for (const line of lines) {
    const fenceMatch = /^[ \t]{0,3}(`{3,}|~{3,})/.exec(line);
    if (fenceMatch?.[1]) {
      const marker = fenceMatch[1];
      const markerChar = marker[0] ?? "";
      if (inFence && markerChar === fenceChar && marker.length >= fenceLength) {
        output += line;
        inFence = false;
        fenceChar = "";
        fenceLength = 0;
      } else if (!inFence) {
        flushProse();
        output += line;
        inFence = true;
        fenceChar = markerChar;
        fenceLength = marker.length;
      } else {
        output += line;
      }
      continue;
    }

    if (inFence) output += line;
    else prose += line;
  }

  flushProse();
  return output;
}

function normalizeGeneratedMarkdownProse(content: string) {
  return content
    .replace(/"{2,}/g, '" "')
    .replace(/([^\n#])(?=#{1,6}\s*[\u4e00-\u9fffA-Za-z0-9])/g, "$1\n\n")
    .replace(/(^|\n)(#{1,6})([^\s#])/g, "$1$2 $3")
    .replace(/(^|\n)##\s*(\d+\.\d+)/g, "$1### $2")
    .replace(/(^|\n)(#{1,6}\s+[^\n>]{1,100})>\s*/g, "$1$2\n\n> ")
    .replace(/(^|\n)(#{1,6}\s+[^\n]*?)\s*-{3,}\s*/g, "$1$2\n\n---\n")
    .replace(
      /(^|\n)(#{1,6}\s+[一二三四五六七八九十]+、[^。\n]{0,28}?(?:判断|建议|分析|结论|路线|方法|内容))(?=[\u4e00-\u9fffA-Za-z0-9])/g,
      "$1$2\n\n",
    )
    .replace(/(^|\n)(#{1,6}\s+[^|\n]{1,80})\|/g, "$1$2\n\n|")
    .replace(/(^|\n)(#{1,6}\s+[^\n]*?)(\d+\.\s)/g, "$1$2\n\n$3")
    .replace(/([\u4e00-\u9fff，。；：、)])(\d+\.\s)/g, "$1\n$2")
    .replace(/([^\s\n])-[ \t]+(?=[A-Z\u4e00-\u9fff])/g, "$1\n- ")
    .replace(/(^|\n)(\s*)(\d+(?:\.\d+)+)([^\s\d.])/g, "$1$2$3 $4");
}

export function normalizeAssistantMarkdown(content: string) {
  return normalizeOutsideFencedCode(content, normalizeGeneratedMarkdownProse).replace(
    webCitationPattern,
    "[$1]($2)",
  );
}

function addCitation(citations: AssistantCitation[], next: AssistantCitation) {
  const key = `${next.kind}:${next.title}:${next.detail ?? ""}:${next.href ?? ""}`;
  if (
    citations.some(
      (item) => `${item.kind}:${item.title}:${item.detail ?? ""}:${item.href ?? ""}` === key,
    )
  ) {
    return;
  }
  citations.push(next);
}

export function prepareAssistantContent(content: string): {
  content: string;
  citations: AssistantCitation[];
} {
  const citations: AssistantCitation[] = [];
  let normalized = normalizeAssistantMarkdown(content);

  normalized = normalized.replace(knowledgeCitationPattern, (_match, raw: string) => {
    const parts = raw
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
    const title = parts[0] ?? "知识库来源";
    const detail = parts.slice(1).join(" | ") || undefined;
    addCitation(citations, { kind: "knowledge", title, detail });
    return "";
  });

  normalized.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, (_match, title: string, href: string) => {
    addCitation(citations, { kind: "web", title: title.trim(), href: href.trim() });
    return _match;
  });

  normalized = normalized.replace(bareCitationPattern, (_match, raw: string) => {
    const title = raw.trim();
    if (title) addCitation(citations, { kind: "web", title });
    return "";
  });

  return {
    content: normalized.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim(),
    citations,
  };
}
