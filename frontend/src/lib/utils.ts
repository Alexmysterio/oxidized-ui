import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function humanizeKey(value: string): string {
  return value
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function initials(value: string): string {
  return value
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function safeJsonParse<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

export function truncate(value: string, length = 60): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

export function getPath(source: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((value, key) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return (value as Record<string, unknown>)[key];
    }
    return undefined;
  }, source);
}

export function setPath(source: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const clone = structuredClone(source);
  const keys = path.split(".");
  let target: Record<string, unknown> = clone;
  keys.slice(0, -1).forEach((key) => {
    const current = target[key];
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      target[key] = {};
    }
    target = target[key] as Record<string, unknown>;
  });
  const last = keys[keys.length - 1];
  if (value === undefined || value === "") {
    delete target[last];
  } else {
    target[last] = value;
  }
  return clone;
}

export function removeEmpty(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(removeEmpty).filter((item) => item !== "" && item !== undefined && item !== null);
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .map(([key, item]) => [key, removeEmpty(item)])
        .filter(([, item]) => item !== "" && item !== undefined),
    );
  }
  return value;
}

export function copyToClipboard(value: string): Promise<void> {
  return navigator.clipboard.writeText(value);
}
