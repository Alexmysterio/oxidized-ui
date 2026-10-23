import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock3, GitCompareArrows, History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DiffView } from "@/components/shared/diff-view";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useIntl } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { notifyError } from "@/lib/errors";
import type { Revision } from "@/types/api";

const statusVariant = {
  applied: "success",
  draft: "warning",
  superseded: "secondary",
  discarded: "outline",
  rolled_back: "destructive",
} as const;

export function ConfigRevisionsSheet({
  open,
  onOpenChange,
  appliedId,
  draftId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  appliedId: number | null;
  draftId: number | null;
}) {
  const { t } = useTranslation();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const [diffRevision, setDiffRevision] = useState<Revision | null>(null);
  const [restoreRevision, setRestoreRevision] = useState<Revision | null>(null);

  const revisionsQuery = useQuery({
    queryKey: ["config-revisions"],
    queryFn: () => api.configRevisions(1, 50),
    enabled: open,
  });
  const diffQuery = useQuery({
    queryKey: ["config-revision-diff", diffRevision?.id],
    queryFn: () => api.configRevisionDiff(diffRevision!.id),
    enabled: Boolean(diffRevision),
  });
  const restore = useMutation({
    mutationFn: (revision: Revision) => api.restoreConfigRevision(revision.id),
    onSuccess: () => {
      toast.success(t("config.restored"));
      setRestoreRevision(null);
      void queryClient.invalidateQueries({ queryKey: ["config"] });
      void queryClient.invalidateQueries({ queryKey: ["config-revisions"] });
    },
    onError: (error) => notifyError(t, error),
  });

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent className="w-[min(94vw,44rem)] gap-0 p-0">
          <SheetHeader className="border-b pb-5 pt-6">
            <SheetTitle className="flex items-center gap-2">
              <History className="h-4 w-4 text-primary" />
              {t("config.revisionHistory")}
            </SheetTitle>
            <SheetDescription>{t("config.revisionHistoryDescription")}</SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto p-4">
            {revisionsQuery.isLoading ? (
              <div className="space-y-2">
                {[0, 1, 2, 3].map((item) => <div key={item} className="h-20 animate-pulse rounded-md bg-muted" />)}
              </div>
            ) : revisionsQuery.isError ? (
              <ErrorState onRetry={() => void revisionsQuery.refetch()} compact />
            ) : !revisionsQuery.data?.items.length ? (
              <EmptyState icon={History} title={t("config.noRevisions")} compact />
            ) : (
              <div className="space-y-2">
                {revisionsQuery.data.items.map((revision) => (
                  <div key={revision.id} className="rounded-lg border bg-card p-3 shadow-xs">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs font-semibold">#{revision.id}</span>
                      <Badge variant={statusVariant[revision.status] ?? "outline"}>{t(`config.revisionStatus.${revision.status}`, { defaultValue: revision.status })}</Badge>
                      {appliedId === revision.id ? <Badge variant="outline">{t("config.applied")}</Badge> : null}
                      {draftId === revision.id ? <Badge variant="outline">{t("config.draft")}</Badge> : null}
                      <span className="ml-auto inline-flex items-center gap-1 font-mono text-[9px] text-muted-foreground">
                        <Clock3 className="h-3 w-3" />
                        {intl.relative(revision.created_at)}
                      </span>
                    </div>
                    <div className="mt-2 grid gap-x-4 gap-y-1 text-[11px] text-muted-foreground sm:grid-cols-2">
                      <span>{t("config.origin")}: <span className="font-mono">{revision.origin}</span></span>
                      <span>{t("config.author")}: <span className="font-mono">{revision.created_by_id ? `#${revision.created_by_id}` : t("config.unknownUser")}</span></span>
                      <span>{t("config.created")}: {intl.dateTime(revision.created_at)}</span>
                      {revision.applied_at ? <span>{t("config.appliedAt")}: {intl.dateTime(revision.applied_at)}</span> : null}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button variant="outline" size="xs" onClick={() => setDiffRevision(revision)}>
                        <GitCompareArrows />
                        {t("config.viewDiff")}
                      </Button>
                      <Button variant="ghost" size="xs" onClick={() => setRestoreRevision(revision)}>
                        <RotateCcw />
                        {t("config.restore")}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </SheetContent>
      </Sheet>

      <Dialog open={Boolean(diffRevision)} onOpenChange={(next) => !next && setDiffRevision(null)}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>{t("config.revisionDiff")}</DialogTitle>
            <DialogDescription>
              #{diffRevision?.id} · {t("config.againstApplied")}
            </DialogDescription>
          </DialogHeader>
          {diffQuery.isLoading ? (
            <div className="h-64 animate-pulse rounded-lg bg-muted" />
          ) : diffQuery.isError ? (
            <ErrorState onRetry={() => void diffQuery.refetch()} compact />
          ) : diffQuery.data ? (
            <DiffView diff={diffQuery.data} fromLabel={t("config.applied")} toLabel={`#${diffRevision?.id}`} />
          ) : null}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(restoreRevision)}
        onOpenChange={(next) => !next && setRestoreRevision(null)}
        title={t("config.restoreTitle")}
        description={t("config.restoreDescription", { id: restoreRevision?.id ?? "" })}
        confirmLabel={t("config.restore")}
        destructive={false}
        loading={restore.isPending}
        onConfirm={() => restoreRevision && restore.mutate(restoreRevision)}
      />
    </>
  );
}
