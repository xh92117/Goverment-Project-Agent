export const UNTITLED_DIRECT_THREAD_TITLE = "待命名对话";
export const UNTITLED_PROJECT_THREAD_TITLE = "待命名项目对话";

const LEADING_REQUEST_WORDS =
  /^(请|麻烦|劳烦|帮我|帮忙|请帮我|请你|请您|我想|我需要|能否|可以|麻烦你|麻烦您|协助我|为我)+/;

export function summarizeThreadTitle(prompt: string, fallback = UNTITLED_DIRECT_THREAD_TITLE) {
  const normalized = prompt
    .replace(/\s+/g, " ")
    .replace(/[“”"'`]+/g, "")
    .trim();
  if (!normalized) return fallback;

  const title = normalized
    .replace(LEADING_REQUEST_WORDS, "")
    .replace(/^[，,。！？!?.；;：:\s]+/, "")
    .replace(/[，,。！？!?.；;：:\s]+$/, "")
    .trim();
  const firstClause = title.split(/[，,。！？!?.；;：:]/)[0]?.trim();
  const compact = firstClause?.trim() ? firstClause : title ? title : normalized;
  return compact.length > 24 ? `${compact.slice(0, 24)}...` : compact;
}
