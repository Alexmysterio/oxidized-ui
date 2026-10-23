import { Columns2, Rows3 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DiffLine, DiffResult } from "@/types/api";
import { cn } from "@/lib/utils";

type DiffMode = "split" | "unified";

function lineClass(type: "same" | "added" | "removed" | "changed") {
  return {
    same: "text-muted-foreground",
    added: "bg-success/[0.08] text-success",
    removed: "bg-destructive/[0.07] text-destructive",
    changed: "bg-warning/[0.08] text-warning",
  }[type];
}

function DiffText({ line }: { line: DiffLine | null }) {
  if (!line) return null;
  if (!line.segments?.length) return <>{line.text}</>;
  return (
    <>
      {line.segments.map((segment, index) => (
        <span key={index} className={segment.changed ? "rounded-sm bg-warning/25 px-0.5" : undefined}>
          {segment.text}
        </span>
      ))}
    </>
  );
}

export function DiffView({
  diff,
  defaultMode = "split",
  fromLabel,
  toLabel,
  className,
}: {
  diff: DiffResult;
  defaultMode?: DiffMode;
  fromLabel?: string;
  toLabel?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<DiffMode>(defaultMode);
  const hasChanges = diff.side_by_side.some((row) => row.type !== "same");
  return (
    <div className={cn("overflow-hidden rounded-lg border bg-card", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/30 px-3 py-2">
        <div className="flex items-center gap-2">
          <Badge variant="success" className="normal-case tracking-normal">
            {t("nodeDetail.additions", { count: diff.stats.additions })}
          </Badge>
          <Badge variant="destructive" className="normal-case tracking-normal">
            {t("nodeDetail.deletions", { count: diff.stats.deletions })}
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="icon-xs"
            variant={mode === "split" ? "secondary" : "ghost"}
            onClick={() => setMode("split")}
            aria-label={t("diff.split")}
            title={t("diff.split")}
          >
            <Columns2 />
          </Button>
          <Button
            type="button"
            size="icon-xs"
            variant={mode === "unified" ? "secondary" : "ghost"}
            onClick={() => setMode("unified")}
            aria-label={t("diff.unified")}
            title={t("diff.unified")}
          >
            <Rows3 />
          </Button>
        </div>
      </div>
      {!hasChanges ? (
        <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("nodeDetail.noChanges")}</p>
      ) : mode === "split" ? (
        <div className="max-h-[62vh] overflow-auto">
          <div className="grid min-w-[720px] grid-cols-2 divide-x">
            <div className="border-b bg-muted/20 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {fromLabel ?? t("common.from")}
            </div>
            <div className="border-b bg-muted/20 px-3 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              {toLabel ?? t("common.to")}
            </div>
            {diff.side_by_side.map((row, index) => (
              <div key={index} className="contents">
                <div
                  className={cn(
                    "flex min-h-[24px] gap-3 px-3 py-0.5 font-mono text-[12px] leading-5",
                    row.type === "removed" || row.type === "changed" ? lineClass(row.type) : "text-muted-foreground",
                  )}
                >
                  <span className="w-8 shrink-0 select-none text-right text-[10px] opacity-50">{row.left?.line ?? ""}</span>
                  <span className="whitespace-pre-wrap break-all"><DiffText line={row.left} /></span>
                </div>
                <div
                  className={cn(
                    "flex min-h-[24px] gap-3 px-3 py-0.5 font-mono text-[12px] leading-5",
                    row.type === "added" || row.type === "changed" ? lineClass(row.type) : "text-muted-foreground",
                  )}
                >
                  <span className="w-8 shrink-0 select-none text-right text-[10px] opacity-50">{row.right?.line ?? ""}</span>
                  <span className="whitespace-pre-wrap break-all"><DiffText line={row.right} /></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="max-h-[62vh] overflow-auto py-2">
          {diff.unified ? (
            diff.unified.split(/\r?\n/).map((line, index) => {
              const added = line.startsWith("+") && !line.startsWith("+++");
              const removed = line.startsWith("-") && !line.startsWith("---");
              return (
                <div
                  key={index}
                  className={cn(
                    "whitespace-pre-wrap break-all px-4 font-mono text-[12px] leading-5",
                    added ? "bg-success/[0.08] text-success" : removed ? "bg-destructive/[0.07] text-destructive" : "text-muted-foreground",
                  )}
                >
                  {line || " "}
                </div>
              );
            })
          ) : (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">{t("nodeDetail.noChanges")}</p>
          )}
        </div>
      )}
    </div>
  );
}
