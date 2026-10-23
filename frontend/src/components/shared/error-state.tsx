import { RotateCcw, TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ErrorState({
  onRetry,
  compact = false,
  className,
}: {
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-destructive/20 bg-destructive/[0.03] text-center",
        compact ? "px-5 py-8" : "px-6 py-14",
        className,
      )}
    >
      <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border border-destructive/20 bg-destructive/10 text-destructive">
        <TriangleAlert className="h-5 w-5" />
      </div>
      <p className="text-sm font-medium">{t("common.loadingError")}</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{t("common.loadingErrorDescription")}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RotateCcw />
          {t("common.retry")}
        </Button>
      ) : null}
    </div>
  );
}
