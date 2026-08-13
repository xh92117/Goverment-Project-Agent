export function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function compactNumber(value?: number | null) {
  if (typeof value !== "number") return "0";
  return new Intl.NumberFormat("zh-CN", { notation: "compact" }).format(value);
}
