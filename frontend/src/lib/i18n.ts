import i18n from "i18next";
import HttpBackend from "i18next-http-backend";
import { initReactI18next } from "react-i18next";

import type { Meta } from "@/types/api";

export const LANGUAGE_STORAGE_KEY = "oxidized-ui-language";
export const THEME_STORAGE_KEY = "oxidized-ui-theme";
export const FALLBACK_LANGUAGES = ["es", "en"];
export const FALLBACK_LANGUAGE = "es";

export const languageNames: Record<string, string> = {
  es: "Español",
  en: "English",
};

function storedLanguage(): string | null {
  try {
    return localStorage.getItem(LANGUAGE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function browserLanguage(): string | null {
  const candidates = navigator.languages?.length ? navigator.languages : [navigator.language];
  for (const candidate of candidates) {
    const base = candidate.split("-")[0]?.toLowerCase();
    if (base) return base;
  }
  return null;
}

export function pickLanguage(meta: Meta | null): { language: string; persisted: boolean } {
  const available = meta?.available_languages?.length ? meta.available_languages : FALLBACK_LANGUAGES;
  const stored = storedLanguage();
  if (stored && available.includes(stored)) return { language: stored, persisted: true };
  const browser = browserLanguage();
  if (browser && available.includes(browser)) return { language: browser, persisted: false };
  const fallback = meta?.default_language && available.includes(meta.default_language) ? meta.default_language : FALLBACK_LANGUAGE;
  return { language: fallback, persisted: false };
}

export async function loadInitialMeta(): Promise<Meta | null> {
  try {
    const response = await fetch("/api/meta", { credentials: "include", cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as Meta;
  } catch {
    return null;
  }
}

export async function initializeI18n(meta: Meta | null): Promise<string> {
  const choice = pickLanguage(meta);
  const fallback = meta?.default_language ?? FALLBACK_LANGUAGE;
  await i18n
    .use(HttpBackend)
    .use(initReactI18next)
    .init({
      lng: choice.language,
      fallbackLng: fallback,
      supportedLngs: meta?.available_languages?.length ? meta.available_languages : FALLBACK_LANGUAGES,
      load: "languageOnly",
      backend: {
        loadPath: "/locales/{{lng}}.json",
      },
      interpolation: { escapeValue: false },
      react: { useSuspense: false },
      returnNull: false,
      keySeparator: ".",
      nsSeparator: false,
    });
  document.documentElement.lang = choice.language;
  return choice.language;
}

export async function changeLanguage(language: string, options?: { persist?: boolean }): Promise<void> {
  await i18n.changeLanguage(language);
  document.documentElement.lang = language;
  if (options?.persist !== false) {
    try {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // localStorage can be unavailable in hardened browsers.
    }
  }
}

export function currentLanguage(): string {
  return i18n.resolvedLanguage?.split("-")[0] ?? i18n.language ?? FALLBACK_LANGUAGE;
}

export default i18n;
