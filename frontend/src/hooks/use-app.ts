import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/lib/auth";
import { formatDate, formatDateTime, formatNumber, formatRelative } from "@/lib/format";

export function useLocale() {
  const { i18n } = useTranslation();
  return i18n.resolvedLanguage?.split("-")[0] ?? i18n.language ?? "es";
}

export function useIntl() {
  const { meta } = useAuth();
  const language = useLocale();
  const timeZone = meta?.timezone ?? undefined;
  return {
    language,
    timeZone,
    date: (value?: string | null) => formatDate(value, language, timeZone),
    dateTime: (value?: string | null) => formatDateTime(value, language, timeZone),
    relative: (value?: string | null) => formatRelative(value, language),
    number: (value: number) => formatNumber(value, language),
  };
}

export function usePageTitle(titleKey?: string) {
  const { t } = useTranslation();
  const { meta } = useAuth();
  useEffect(() => {
    if (!titleKey) return;
    document.title = `${t(titleKey)} · ${meta?.site_name || t("app.name")}`;
  }, [titleKey, t, meta?.site_name]);
}
