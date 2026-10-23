import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

export function BrandMark({ className, animated = false }: { className?: string; animated?: boolean }) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" className={cn("h-9 w-9", className)}>
      <rect width="48" height="48" rx="12" fill="hsl(var(--primary))" />
      <circle cx="24" cy="24" r="12.5" stroke="white" strokeOpacity="0.35" strokeWidth="1.5" />
      <circle cx="24" cy="24" r="4.5" fill="white" />
      <circle cx="24" cy="9" r="3" fill="white" fillOpacity="0.92" />
      <circle cx="37" cy="31" r="3" fill="white" fillOpacity="0.92" />
      <circle cx="11" cy="31" r="3" fill="white" fillOpacity="0.92" />
      <path d="M24 13v7M28 26l6.5 3.5M20 26l-6.5 3.5" stroke="white" strokeOpacity="0.8" strokeWidth="1.3" />
      {animated && (
        <circle cx="24" cy="9" r="3" fill="white">
          <animate attributeName="opacity" values="1;.35;1" dur="3.2s" repeatCount="indefinite" />
        </circle>
      )}
    </svg>
  );
}

export function BrandLockup({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { t } = useTranslation();
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <BrandMark animated />
      {!compact && (
        <div className="leading-tight">
          <div className="text-[15px] font-semibold tracking-tight text-sidebar-foreground">{t("app.name")}</div>
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-sidebar-muted">{t("app.taglineShort")}</div>
        </div>
      )}
    </div>
  );
}
