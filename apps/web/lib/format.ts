export function formatNumber(value: number | null | undefined, options: { compact?: boolean; decimals?: number } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const { compact = false, decimals } = options;
  if (compact) {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
  }
  const fractionDigits = decimals ?? (Number.isInteger(value) ? 0 : 2);
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: fractionDigits }).format(value);
}

export function formatMetric(value: number | null | undefined, format = "number") {
  if (value === null || value === undefined) return "—";
  const abs = Math.abs(value);
  const compact = abs >= 100000;
  const base = compact
    ? new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value)
    : new Intl.NumberFormat("en-US", { maximumFractionDigits: format === "integer" ? 0 : abs < 100 ? 2 : 1 }).format(value);
  if (format === "currency") return `₹${base}`;
  if (format === "percent") return `${(value * 100).toFixed(1)}%`;
  return base;
}

export function formatDate(value?: string | null, options: Intl.DateTimeFormatOptions = { month: "short", year: "numeric" }) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", options).format(date);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function relativeTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value).getTime();
  const diff = Date.now() - date;
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function titleCase(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function qualityTone(score?: number | null) {
  if (score === null || score === undefined) return { label: "Unknown", tone: "neutral" as const };
  if (score >= 90) return { label: "Excellent", tone: "success" as const };
  if (score >= 75) return { label: "Good", tone: "brand" as const };
  if (score >= 60) return { label: "Fair", tone: "warning" as const };
  return { label: "Needs work", tone: "danger" as const };
}
