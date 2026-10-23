import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact = false,
}: {
  icon: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative flex flex-col items-center justify-center overflow-hidden rounded-lg border border-dashed border-border/80 bg-card/40 text-center",
        compact ? "px-6 py-10" : "px-6 py-16",
        className,
      )}
    >
      <div className="pointer-events-none absolute inset-0 opacity-[0.45] [background-image:radial-gradient(circle_at_50%_20%,hsl(var(--primary)/.08),transparent_55%)]" />
      <div className="relative mb-4 flex h-12 w-12 items-center justify-center rounded-xl border bg-card text-primary shadow-sm">
        <Icon className="h-5 w-5" strokeWidth={1.7} />
      </div>
      <h3 className="relative text-base font-semibold tracking-tight">{title}</h3>
      {description ? (
        <p className="relative mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="relative mt-5 flex flex-wrap items-center justify-center gap-2">{action}</div> : null}
    </div>
  );
}
