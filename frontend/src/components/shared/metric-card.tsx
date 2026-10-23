import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const tones = {
  default: "border-border bg-card text-foreground",
  primary: "border-primary/20 bg-primary/[0.035] text-foreground",
  success: "border-success/20 bg-success/[0.035] text-foreground",
  warning: "border-warning/20 bg-warning/[0.035] text-foreground",
  destructive: "border-destructive/20 bg-destructive/[0.035] text-foreground",
} as const;

export function MetricCard({
  label,
  value,
  icon: Icon,
  hint,
  tone = "default",
  onClick,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  tone?: keyof typeof tones;
  onClick?: () => void;
}) {
  const content = (
    <>
      <div className="flex items-start justify-between gap-3">
        <p className="network-label text-[9px]">{label}</p>
        <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card/80 text-muted-foreground">
          <Icon className="h-3.5 w-3.5" strokeWidth={1.7} />
        </span>
      </div>
      <p className="metric-number mt-3 text-[28px] leading-none">{value}</p>
      {hint ? <p className="mt-2 truncate text-[11px] text-muted-foreground">{hint}</p> : null}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cn(
          "group relative overflow-hidden rounded-lg border p-4 text-left shadow-soft transition-all hover:-translate-y-0.5 hover:shadow-lift",
          tones[tone],
        )}
      >
        {content}
      </button>
    );
  }

  return (
    <div className={cn("relative overflow-hidden rounded-lg border p-4 shadow-soft", tones[tone])}>
      {content}
    </div>
  );
}
