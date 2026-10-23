import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Skeleton } from "@/components/ui/skeleton";
import { BrandMark } from "@/components/shared/brand";
import { cn } from "@/lib/utils";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin", className)} aria-hidden="true" />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-4 w-[34rem] max-w-full" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <Skeleton key={item} className="h-28 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-lg" />
    </div>
  );
}

export function TableSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-1 p-1">
      {Array.from({ length: rows }).map((_, row) => (
        <div key={row} className="flex items-center gap-4 rounded-md px-3 py-3">
          {Array.from({ length: columns }).map((__, column) => (
            <Skeleton key={column} className={cn("h-4", column === 0 ? "w-44" : "w-24")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function BootScreen({ message }: { message?: string }) {
  const { t } = useTranslation();
  return (
    <div className="app-grid grid min-h-screen place-items-center bg-background px-6">
      <div className="flex flex-col items-center gap-5 text-center">
        <div className="relative">
          <span className="absolute inset-0 -z-10 animate-pulse-ring rounded-2xl bg-primary/20" />
          <BrandMark className="h-14 w-14 shadow-lift" animated />
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
            {t("app.name")}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">{message ?? t("app.loading")}</p>
        </div>
        <div className="h-0.5 w-36 overflow-hidden rounded-full bg-muted">
          <div className="h-full w-1/2 animate-[shimmer_1.4s_infinite] bg-primary" />
        </div>
      </div>
    </div>
  );
}
