const dateTimeCache = new Map<string, Intl.DateTimeFormat>();
const dateCache = new Map<string, Intl.DateTimeFormat>();

function formatter(language: string, timeZone: string | null, dateOnly: boolean): Intl.DateTimeFormat {
  const key = `${language}:${timeZone ?? "browser"}:${dateOnly}`;
  const cache = dateOnly ? dateCache : dateTimeCache;
  let value = cache.get(key);
  if (!value) {
    value = new Intl.DateTimeFormat(language, {
      ...(dateOnly
        ? { year: "numeric", month: "short", day: "2-digit" }
        : { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" }),
      ...(timeZone ? { timeZone } : {}),
    });
    cache.set(key, value);
  }
  return value;
}

export function formatDateTime(value?: string | null, language = "es", timeZone?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return formatter(language, timeZone ?? null, false).format(date);
}

export function formatDate(value?: string | null, language = "es", timeZone?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return formatter(language, timeZone ?? null, true).format(date);
}

export function formatRelative(
  value: string | null | undefined,
  language: string,
  now = new Date(),
): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const diff = date.getTime() - now.getTime();
  const seconds = Math.round(diff / 1000);
  const abs = Math.abs(seconds);
  const rtf = new Intl.RelativeTimeFormat(language, { numeric: "auto" });
  if (abs < 60) return rtf.format(seconds, "second");
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(seconds / 86400), "day");
  if (abs < 86400 * 365) return rtf.format(Math.round(seconds / (86400 * 30)), "month");
  return rtf.format(Math.round(seconds / (86400 * 365)), "year");
}

export function formatNumber(value: number, language: string): string {
  return new Intl.NumberFormat(language).format(value);
}

export function formatBytes(value: number, language: string): string {
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(size)} ${units[unit]}`;
}

export function formatTimestampForLog(value: string | null, language: string): string {
  if (!value) return "";
  return formatDateTime(value, language).replace(/^.*?(\d{1,2}:\d{2})/, "$1");
}
