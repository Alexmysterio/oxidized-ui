import { useQuery } from "@tanstack/react-query";
import { Download, FileJson2, Filter, ScrollText, Search, ShieldCheck, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Pagination } from "@/components/shared/pagination";
import { PageHeader } from "@/components/shared/page-header";
import { TableSkeleton } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { AuditEntry } from "@/types/api";

const actionCodes = [
  "auth.login_succeeded",
  "auth.login_failed",
  "auth.logout",
  "auth.password_changed",
  "setup.completed",
  "setup.bootstrap_admin",
  "node.created",
  "node.updated",
  "node.deleted",
  "node.bulk_updated",
  "node.imported",
  "node.backup_requested",
  "site.coordinates_updated",
  "group.created",
  "group.updated",
  "group.deleted",
  "config.draft_saved",
  "config.applied",
  "config.apply_failed",
  "config.apply_requested",
  "config.bootstrap_written",
  "config.external_imported",
  "oxidized.reload_requested",
  "oxidized.restart_requested",
  "oxidized.auto_recovered",
  "user.created",
  "user.updated",
  "user.deleted",
  "user.password_reset",
  "system.settings_updated",
  "system.connection_test",
];

const targetTypes = ["node", "group", "config", "user", "system", "auth"];

interface Filters {
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  from: string;
  to: string;
}

const emptyFilters: Filters = { actor: "", action: "", target_type: "", target_id: "", from: "", to: "" };

export function AuditPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [applied, setApplied] = useState<Filters>(emptyFilters);
  const [page, setPage] = useState(1);
  const [details, setDetails] = useState<AuditEntry | null>(null);
  usePageTitle("nav.audit");

  const auditQuery = useQuery({
    queryKey: ["audit", applied, page],
    queryFn: () =>
      api.audit({
        actor: applied.actor || undefined,
        action: applied.action || undefined,
        target_type: applied.target_type || undefined,
        target_id: applied.target_id || undefined,
        from: applied.from || undefined,
        to: applied.to || undefined,
        page,
        page_size: 30,
      }),
  });

  const apply = () => {
    setApplied(filters);
    setPage(1);
  };
  const reset = () => {
    setFilters(emptyFilters);
    setApplied(emptyFilters);
    setPage(1);
  };

  const entries = auditQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><ShieldCheck className="h-3.5 w-3.5 text-primary" />{t("nav.administration")}</>}
        title={t("audit.title")}
        description={t("audit.subtitle")}
        actions={<Button variant="outline" size="sm" onClick={() => void api.exportAudit().catch((error) => toast.error(t("errors.title"), { description: errorMessage(t, error) }))}><Download />{t("audit.export")}</Button>}
      />

      <div className="rounded-lg border bg-card p-3 shadow-soft">
        <div className="mb-3 flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          <span className="eyebrow">{t("common.filters")}</span>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.actor")}</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input value={filters.actor} onChange={(event) => setFilters({ ...filters, actor: event.target.value })} placeholder={t("audit.filterActor")} className="h-8 pl-8 text-xs" />
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.action")}</Label>
            <Select value={filters.action || "__all__"} onValueChange={(value) => setFilters({ ...filters, action: value === "__all__" ? "" : value })}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{t("audit.filterAction")}</SelectItem>
                {actionCodes.map((code) => <SelectItem key={code} value={code}>{t(`audit.actions.${code}`, { defaultValue: code })}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.target")}</Label>
            <Select value={filters.target_type || "__all__"} onValueChange={(value) => setFilters({ ...filters, target_type: value === "__all__" ? "" : value })}>
              <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{t("audit.allTargets")}</SelectItem>
                {targetTypes.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.targetId")}</Label>
            <Input
              value={filters.target_id}
              onChange={(event) => setFilters({ ...filters, target_id: event.target.value })}
              placeholder="42"
              className="h-8 font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.from")}</Label>
            <Input type="date" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} className="h-8 text-xs" />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] text-muted-foreground">{t("audit.to")}</Label>
            <Input type="date" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} className="h-8 text-xs" />
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button size="sm" onClick={apply}><Filter />{t("audit.applyFilters")}</Button>
          <Button size="sm" variant="ghost" onClick={reset}><X />{t("common.clearFilters")}</Button>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border bg-card shadow-soft">
        {auditQuery.isLoading ? (
          <TableSkeleton rows={8} columns={5} />
        ) : auditQuery.isError ? (
          <div className="p-4"><ErrorState onRetry={() => void auditQuery.refetch()} compact /></div>
        ) : entries.length === 0 ? (
          <div className="p-4"><EmptyState icon={ScrollText} title={t("audit.emptyTitle")} description={t("audit.emptyDescription")} compact /></div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("audit.when")}</TableHead>
                <TableHead>{t("audit.actor")}</TableHead>
                <TableHead>{t("audit.action")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("audit.target")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("audit.ip")}</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="whitespace-nowrap font-mono text-[10px] text-muted-foreground">{intl.dateTime(entry.created_at)}</TableCell>
                  <TableCell>
                    <div>
                      <span className="text-xs font-medium">{entry.actor.role === "system" ? t("audit.systemActor") : entry.actor.username}</span>
                      <span className="ml-1 font-mono text-[9px] uppercase text-muted-foreground">{entry.actor.role}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="text-xs">{t(`audit.actions.${entry.action_code}`, { ...entry.action_params, defaultValue: entry.action_code })}</span>
                  </TableCell>
                  <TableCell className="hidden lg:table-cell">
                    {entry.target_type ? <Badge variant="outline">{entry.target_type}{entry.target_id ? ` #${entry.target_id}` : ""}</Badge> : "—"}
                  </TableCell>
                  <TableCell className="hidden font-mono text-[10px] text-muted-foreground xl:table-cell">{entry.ip ?? "—"}</TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon-xs" onClick={() => setDetails(entry)} aria-label={t("common.details")} title={t("common.details")}>
                      <FileJson2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {auditQuery.data ? <Pagination page={auditQuery.data.page} totalPages={auditQuery.data.total_pages} total={auditQuery.data.total} onPage={setPage} /> : null}
      </div>

      <Dialog open={Boolean(details)} onOpenChange={(open) => !open && setDetails(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("common.details")}</DialogTitle>
            <DialogDescription>
              {details ? t(`audit.actions.${details.action_code}`, { ...details.action_params, defaultValue: details.action_code }) : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-[7rem_1fr] gap-2 rounded-md border bg-muted/20 p-3">
              <span className="text-muted-foreground">{t("audit.actor")}</span>
              <span>{details?.actor.username} · {details?.actor.role}</span>
              <span className="text-muted-foreground">{t("audit.when")}</span>
              <span>{details ? intl.dateTime(details.created_at) : ""}</span>
              <span className="text-muted-foreground">{t("audit.target")}</span>
              <span className="font-mono">{details?.target_type ?? "—"} {details?.target_id ?? ""}</span>
              <span className="text-muted-foreground">{t("audit.ip")}</span>
              <span className="font-mono">{details?.ip ?? "—"}</span>
            </div>
            <div>
              <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{t("audit.details")}</p>
              <pre className="max-h-64 overflow-auto rounded-md border bg-[#070c15] p-3 font-mono text-[10px] leading-relaxed text-slate-300">
                {JSON.stringify(details?.action_params ?? {}, null, 2)}
              </pre>
            </div>
            {details?.action_params?.before && details?.action_params?.after ? (
              <div>
                <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{t("audit.beforeAfter")}</p>
                <div className="overflow-hidden rounded-md border">
                  <div className="grid grid-cols-3 gap-2 border-b bg-muted/30 px-3 py-1.5 text-[10px] font-medium">
                    <span>{t("audit.field")}</span>
                    <span>{t("audit.before")}</span>
                    <span>{t("audit.after")}</span>
                  </div>
                  {Object.keys(details.action_params.before as Record<string, unknown>).map((field) => (
                    <div key={field} className="grid grid-cols-3 gap-2 border-b px-3 py-1.5 font-mono text-[10px] last:border-0">
                      <span className="text-muted-foreground">{field}</span>
                      <span className="break-all text-destructive">
                        {JSON.stringify((details.action_params.before as Record<string, unknown>)[field])}
                      </span>
                      <span className="break-all text-success">
                        {JSON.stringify((details.action_params.after as Record<string, unknown>)[field])}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
