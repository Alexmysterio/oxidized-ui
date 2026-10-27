import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitCompareArrows, RefreshCw, ServerOff, Upload } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";

export function ReconciliationPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  usePageTitle("nav.reconciliation");

  const reportQuery = useQuery({ queryKey: ["reconciliation"], queryFn: api.reconciliation });
  const report = reportQuery.data;

  const importNodes = useMutation({
    mutationFn: () => api.importReconciled(Array.from(selected)),
    onSuccess: (result) => {
      toast.success(t("reconciliation.imported", { count: result.imported.length }));
      setSelected(new Set());
      void queryClient.invalidateQueries({ queryKey: ["reconciliation"] });
      void queryClient.invalidateQueries({ queryKey: ["nodes"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const toggle = (name: string, checked: boolean) => {
    const next = new Set(selected);
    if (checked) next.add(name);
    else next.delete(name);
    setSelected(next);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><GitCompareArrows className="h-3.5 w-3.5 text-primary" />{t("nav.inventory")}</>}
        title={t("nav.reconciliation")}
        description={t("reconciliation.subtitle")}
        actions={
          <Button variant="outline" size="sm" onClick={() => void reportQuery.refetch()} disabled={reportQuery.isFetching}>
            {reportQuery.isFetching ? <Spinner /> : <RefreshCw />}
            {t("common.refresh")}
          </Button>
        }
      />

      {reportQuery.isError ? (
        <ErrorState onRetry={() => void reportQuery.refetch()} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {[
              { label: t("reconciliation.missingInUi"), value: report?.summary.missing_in_ui ?? 0 },
              { label: t("reconciliation.missingInOxidized"), value: report?.summary.missing_in_oxidized ?? 0 },
              { label: t("reconciliation.drift"), value: report?.summary.drift ?? 0 },
            ].map((card) => (
              <Card key={card.label}>
                <CardContent className="pt-5">
                  <p className="text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{card.label}</p>
                  <p className="mt-1 font-mono text-2xl font-semibold">{card.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle className="text-sm">{t("reconciliation.missingInUiTitle")}</CardTitle>
                <CardDescription>{t("reconciliation.missingInUiDescription")}</CardDescription>
              </div>
              {can("nodes.write") ? (
                <Button size="sm" disabled={!selected.size || importNodes.isPending} onClick={() => importNodes.mutate()}>
                  {importNodes.isPending ? <Spinner /> : <Upload />}
                  {t("reconciliation.importSelected", { count: selected.size })}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {!(report?.missing_in_ui ?? []).length ? (
                <EmptyState icon={ServerOff} title={t("reconciliation.noMissing")} description={t("reconciliation.noMissingDescription")} compact />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-9" />
                      <TableHead>{t("nodes.name")}</TableHead>
                      <TableHead>{t("nodes.address")}</TableHead>
                      <TableHead>{t("nodes.group")}</TableHead>
                      <TableHead>{t("nodes.model")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(report?.missing_in_ui ?? []).map((item) => (
                      <TableRow key={item.name}>
                        <TableCell>
                          <Checkbox checked={selected.has(item.name)} onCheckedChange={(value) => toggle(item.name, value === true)} />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{item.name}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">{item.address ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{item.group_name ?? "—"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{item.model ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("reconciliation.driftTitle")}</CardTitle>
              <CardDescription>{t("reconciliation.driftDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {!(report?.drift ?? []).length ? (
                <p className="text-xs text-muted-foreground">{t("reconciliation.noDrift")}</p>
              ) : (
                <div className="divide-y">
                  {(report?.drift ?? []).map((item) => (
                    <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs">
                      <Link to={`/nodes/${item.id}`} className="font-medium hover:text-primary">{item.name}</Link>
                      <div className="flex flex-wrap gap-2">
                        {Object.entries(item.changes).map(([field, change]) => (
                          <Badge key={field} variant="warning">
                            {field}: {change.ui ?? "—"} → {change.oxidized ?? "—"}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("reconciliation.missingInOxidizedTitle")}</CardTitle>
              <CardDescription>{t("reconciliation.missingInOxidizedDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {!(report?.missing_in_oxidized ?? []).length ? (
                <p className="text-xs text-muted-foreground">{t("reconciliation.noOrphans")}</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(report?.missing_in_oxidized ?? []).map((item) => (
                    <Link
                      key={item.id}
                      to={`/nodes/${item.id}`}
                      className="rounded-md border px-2 py-1 font-mono text-[11px] hover:border-primary/40 hover:text-primary"
                    >
                      {item.name}
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
