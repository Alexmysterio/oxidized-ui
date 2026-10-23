import { CheckCircle2, CircleDashed, Clock3, MinusCircle, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import type { NodeStatus, OxidizedState } from "@/types/api";
import { cn } from "@/lib/utils";

export function NodeStatusBadge({
  status,
  className,
  showIcon = true,
}: {
  status: NodeStatus;
  className?: string;
  showIcon?: boolean;
}) {
  const { t } = useTranslation();
  const config = {
    ok: { variant: "success" as const, Icon: CheckCircle2 },
    failed: { variant: "destructive" as const, Icon: TriangleAlert },
    pending: { variant: "warning" as const, Icon: Clock3 },
    never: { variant: "outline" as const, Icon: MinusCircle },
  }[status];
  const Icon = config.Icon;
  return (
    <Badge variant={config.variant} className={cn("normal-case tracking-normal", className)}>
      {showIcon && <Icon className="h-3 w-3" />}
      {t(`nodeStatus.${status}`)}
    </Badge>
  );
}

export function OxidizedStateBadge({
  state,
  className,
  showDot = true,
}: {
  state: OxidizedState;
  className?: string;
  showDot?: boolean;
}) {
  const { t } = useTranslation();
  const styles: Record<OxidizedState, string> = {
    online: "border-success/25 bg-success/10 text-success",
    offline: "border-destructive/25 bg-destructive/10 text-destructive",
    degraded: "border-warning/25 bg-warning/10 text-warning",
    starting: "border-info/25 bg-info/10 text-info",
    unknown: "border-border bg-muted text-muted-foreground",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em]",
        styles[state],
        className,
      )}
    >
      {showDot ? (
        <span className="relative flex h-1.5 w-1.5">
          <span
            className={cn(
              "absolute inline-flex h-full w-full rounded-full opacity-60",
              state === "online" && "animate-ping bg-success",
              state === "degraded" && "animate-ping bg-warning",
              state === "starting" && "animate-ping bg-info",
            )}
          />
          <span
            className={cn(
              "relative inline-flex h-1.5 w-1.5 rounded-full",
              state === "online" && "bg-success",
              state === "offline" && "bg-destructive",
              state === "degraded" && "bg-warning",
              state === "starting" && "bg-info",
              state === "unknown" && "bg-muted-foreground",
            )}
          />
        </span>
      ) : null}
      {t(`status.${state}`)}
    </span>
  );
}

export function StatusBadge({
  tone,
  children,
  className,
}: {
  tone: "default" | "success" | "warning" | "destructive" | "info" | "outline" | "secondary";
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Badge variant={tone === "default" ? "default" : tone} className={cn("normal-case tracking-normal", className)}>
      {children}
    </Badge>
  );
}

export function NeverBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs text-muted-foreground", className)}>
      <CircleDashed className="h-3.5 w-3.5" />
      {t("common.never")}
    </span>
  );
}
