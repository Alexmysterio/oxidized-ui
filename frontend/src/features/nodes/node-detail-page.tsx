import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpRight,
  CalendarClock,
  Code2,
  Copy,
  Download,
  Fingerprint,
  MoreHorizontal,
  Network,
  PlugZap,
  Pencil,
  RefreshCw,
  ServerCog,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { CodeEditor } from "@/components/shared/code-editor";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DiffView } from "@/components/shared/diff-view";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageSkeleton, Spinner } from "@/components/shared/loaders";
import { CopyButton } from "@/components/shared/copy-button";
import { NodeStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { NodeFormSheet } from "@/features/nodes/node-form-sheet";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Version } from "@/types/api";

function InfoRow({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/60 py-2.5 last:border-0">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className={cn("min-w-0 text-right text-xs", mono && "font-mono text-[11px]")}>{children}</span>
    </div>
  );
}

function VersionContentDialog({
  nodeId,
  version,
  onOpenChange,
}: {
  nodeId: number;
  version: Version | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const intl = useIntl();
  const contentQuery = useQuery({
    queryKey: ["node-version", nodeId, version?.oid],
    queryFn: () => api.nodeVersion(nodeId, version!.oid),
    enabled: Boolean(version),
  });
  return (
    <Dialog open={Boolean(version)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-mono">
            <Code2 className="h-4 w-4 text-primary" />
            {version ? version.oid.slice(0, 12) : ""}
          </DialogTitle>
          <DialogDescription>
            {version ? `${intl.dateTime(version.time)} · ${version.author ?? "—"}` : ""}
          </DialogDescription>
        </DialogHeader>
        {contentQuery.isLoading ? (
          <div className="h-64 animate-pulse rounded-md bg-muted" />
        ) : contentQuery.isError ? (
          <ErrorState onRetry={() => void contentQuery.refetch()} compact />
        ) : (
          <>
            <CodeEditor value={contentQuery.data?.content ?? ""} readOnly language="text" minHeight={320} maxHeight={480} />
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] text-muted-foreground">
                {formatBytes(new Blob([contentQuery.data?.content ?? ""]).size, intl.language)}
              </span>
              <div className="flex gap-2">
                <CopyButton value={contentQuery.data?.content ?? ""} />
                <Button variant="outline" size="sm" onClick={() => void api.downloadNode(nodeId, version?.oid)}>
                  <Download />
                  {t("common.download")}
                </Button>
              </div>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function NodeDetailPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { id } = useParams();
  const nodeId = Number(id);
  const navigate = useNavigate();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [trustOpen, setTrustOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [versionDialog, setVersionDialog] = useState<Version | null>(null);
  usePageTitle("nav.nodes");

  const nodeQuery = useQuery({
    queryKey: ["node", nodeId],
    queryFn: () => api.node(nodeId),
    enabled: Number.isFinite(nodeId),
  });
  const statusQuery = useQuery({
    queryKey: ["node-status", nodeId],
    queryFn: () => api.nodeStatus(nodeId, true),
    enabled: Number.isFinite(nodeId),
    refetchInterval: (query) => (query.state.data?.active_job_id ? 3_000 : 15_000),
  });
  const configQuery = useQuery({
    queryKey: ["node-config", nodeId],
    queryFn: () => api.nodeConfig(nodeId),
    enabled: tab === "configuration" && Number.isFinite(nodeId),
  });
  const versionsQuery = useQuery({
    queryKey: ["node-versions", nodeId],
    queryFn: () => api.nodeVersions(nodeId),
    enabled: (tab === "versions" || tab === "diff") && Number.isFinite(nodeId),
  });

  const historyQuery = useQuery({
    queryKey: ["node-history", nodeId],
    queryFn: () => api.nodeHistory(nodeId),
    enabled: tab === "history" && Number.isFinite(nodeId),
  });

  const versions = versionsQuery.data?.versions ?? [];
  useEffect(() => {
    setSelected(versions.length > 1 ? [versions[1].oid, versions[0].oid] : []);
  }, [versions]);

  const diffQuery = useQuery({
    queryKey: ["node-diff", nodeId, ...selected],
    queryFn: () => api.nodeDiff(nodeId, selected[0], selected[1]),
    enabled: tab === "diff" && selected.length === 2,
  });

  const backup = useMutation({
    mutationFn: () => api.backupNode(nodeId),
    onSuccess: () => {
      toast.success(t("nodeDetail.backupQueued"));
      void queryClient.invalidateQueries({ queryKey: ["node", nodeId] });
      void queryClient.invalidateQueries({ queryKey: ["node-status", nodeId] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteNode(nodeId),
    onSuccess: () => {
      toast.success(t("nodes.deleteSuccess"));
      void queryClient.invalidateQueries({ queryKey: ["nodes"] });
      navigate("/nodes", { replace: true });
    },
    onError: (error) => notifyError(t, error),
  });

  const testConnection = useMutation({
    mutationFn: () => api.testNodeConnection(nodeId),
    onSuccess: (result) => {
      if (result.authenticated) {
        toast.success(t("nodeDetail.connectionOk"));
      } else {
        const reason =
          result.message === "host_key_unknown"
            ? t("errors.node.host_key_unknown")
            : result.message === "authentication_failed"
              ? t("errors.node.auth_failed", { user: node.username ?? "?" })
              : result.message === "missing_credentials"
                ? t("errors.node.missing_credentials")
                : result.message ?? t("errors.generic");
        toast.error(t("nodeDetail.connectionFailed", { reason }));
      }
    },
    onError: (error) => notifyError(t, error),
  });

  const trustHostKey = useMutation({
    mutationFn: () => api.trustHostKey(nodeId),
    onSuccess: (data) => {
      toast.success(t("nodeDetail.trustHostKeySuccess", { fingerprint: data.fingerprints[0] ?? "—" }));
      setTrustOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["node", nodeId] });
      void queryClient.invalidateQueries({ queryKey: ["node-status", nodeId] });
    },
    onError: (error) => notifyError(t, error),
  });

  if (nodeQuery.isLoading) return <PageSkeleton />;
  if (nodeQuery.isError || !nodeQuery.data) {
    return <ErrorState onRetry={() => void nodeQuery.refetch()} />;
  }

  const node = nodeQuery.data;
  const status = statusQuery.data;
  const duration =
    status?.last_started_at && status?.last_finished_at
      ? Math.max(0, Math.round((new Date(status.last_finished_at).getTime() - new Date(status.last_started_at).getTime()) / 1000))
      : null;

  const toggleVersion = (oid: string) => {
    setSelected((current) => {
      if (current.includes(oid)) return current.filter((item) => item !== oid);
      if (current.length >= 2) return [current[1], oid];
      return [...current, oid];
    });
  };

  return (
    <div className="space-y-6">
      <Button variant="ghost" size="sm" className="-ml-2 w-fit text-muted-foreground" asChild>
        <Link to="/nodes">
          <ArrowLeft />
          {t("nodeDetail.back")}
        </Link>
      </Button>

      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="eyebrow inline-flex items-center gap-1.5">
              <Network className="h-3 w-3 text-primary" />
              {t("nav.nodes")}
            </span>
            <span className="text-muted-foreground/40">/</span>
            <span className="font-mono text-[10px] text-muted-foreground">{node.model}</span>
            {node.group_name ? (
              <>
                <span className="text-muted-foreground/40">/</span>
                <span className="font-mono text-[10px] text-muted-foreground">{node.group_name}</span>
              </>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-[-0.025em] md:text-[30px]">{node.name}</h1>
            <NodeStatusBadge status={status?.status ?? node.status} />
          </div>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {node.address ?? "—"} · {t("common.updatedAt")} {intl.relative(node.updated_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {can("backups.trigger") ? (
            <Button size="sm" onClick={() => backup.mutate()} disabled={backup.isPending} title={t("nodeDetail.backupNowHint")}>
              {backup.isPending ? <Spinner /> : <ServerCog />}
              {t("nodeDetail.backupNow")}
            </Button>
          ) : null}
          {can("nodes.write") ? (
            <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}>
              <Pencil />
              {t("nodeDetail.edit")}
            </Button>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon-sm" aria-label={t("common.more")}>
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => void api.downloadNode(nodeId)}>
                <Download />
                {t("nodeDetail.downloadConfig")}
              </DropdownMenuItem>
              {can("nodes.write") ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onSelect={() => testConnection.mutate()}>
                    <PlugZap />
                    {t("nodeDetail.testConnection")}
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => setTrustOpen(true)}>
                    <Fingerprint />
                    {t("nodeDetail.trustHostKey")}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem className="text-destructive focus:text-destructive" onSelect={() => setDeleteOpen(true)}>
                    <Trash2 />
                    {t("nodeDetail.delete")}
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {node.warnings.length ? (
        <div className="flex gap-3 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="space-y-1">
            {node.warnings.map((warning, index) => (
              <p key={`${warning}-${index}`}>{t(`errors.${warning}`, { defaultValue: warning })}</p>
            ))}
          </div>
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto w-full justify-start overflow-x-auto rounded-lg border bg-card p-1 shadow-xs sm:w-auto">
          <TabsTrigger value="overview">{t("nodeDetail.overview")}</TabsTrigger>
          <TabsTrigger value="configuration">{t("nodeDetail.configuration")}</TabsTrigger>
          <TabsTrigger value="versions">{t("nodeDetail.versions")}</TabsTrigger>
          <TabsTrigger value="diff">{t("nodeDetail.diff")}</TabsTrigger>
          <TabsTrigger value="history">{t("nodeDetail.history")}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-5">
          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-1">
              <CardHeader>
                <CardTitle>{t("nodeDetail.connectionInfo")}</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <InfoRow label={t("nodeForm.address")} mono>{node.address ?? "—"}</InfoRow>
                <InfoRow label={t("nodes.input")} mono>{node.input ?? "—"}</InfoRow>
                <InfoRow label={t("nodes.port")} mono>{node.port ?? "—"}</InfoRow>
                <InfoRow label={t("nodes.username")} mono>{node.username ?? "—"}</InfoRow>
                <InfoRow label={t("nodes.credentials")}>
                  <span className="inline-flex flex-wrap justify-end gap-1">
                    {node.has_password ? <Badge variant="success">{t("nodes.hasPassword")}</Badge> : null}
                    {node.has_enable ? <Badge variant="info">{t("nodes.hasEnable")}</Badge> : null}
                    {!node.has_password && !node.has_enable ? <span className="text-muted-foreground">—</span> : null}
                  </span>
                </InfoRow>
                <InfoRow label={t("nodeForm.output")} mono>{node.output ?? "—"}</InfoRow>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t("nodeDetail.inventoryInfo")}</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <InfoRow label={t("nodeForm.model")} mono>{node.model}</InfoRow>
                <InfoRow label={t("nodeForm.group")} mono>{node.group_name ?? "—"}</InfoRow>
                <InfoRow label={t("nodeForm.timeout")} mono>{node.timeout_seconds ?? "—"}</InfoRow>
                <InfoRow label={t("nodeForm.prompt")} mono>
                  <span className="line-clamp-2 break-all">{node.prompt ?? "—"}</span>
                </InfoRow>
                <InfoRow label={t("common.updatedAt")}>{intl.dateTime(node.updated_at)}</InfoRow>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div>
                  <CardTitle>{t("common.status")}</CardTitle>
                  <CardDescription>{status ? intl.relative(status.observed_at) : "—"}</CardDescription>
                </div>
                <Button variant="ghost" size="icon-xs" onClick={() => { void nodeQuery.refetch(); void statusQuery.refetch(); }} aria-label={t("common.refresh")}>
                  {statusQuery.isFetching ? <Spinner /> : <RefreshCw />}
                </Button>
              </CardHeader>
              <CardContent className="pt-0">
                <InfoRow label={t("common.status")}><NodeStatusBadge status={status?.status ?? node.status} /></InfoRow>
                <InfoRow label={t("nodeDetail.lastAttempt")}>{status?.last_finished_at ? intl.dateTime(status.last_finished_at) : node.last_attempt_at ? intl.dateTime(node.last_attempt_at) : t("common.never")}</InfoRow>
                <InfoRow label={t("nodeDetail.lastSuccess")}>{status?.last_success_at ? intl.dateTime(status.last_success_at) : node.last_backup_at ? intl.dateTime(node.last_backup_at) : t("common.never")}</InfoRow>
                {duration !== null ? (
                  <InfoRow label={t("nodeDetail.duration")} mono>{new Intl.NumberFormat(intl.language, { style: "unit", unit: "second", unitDisplay: "short" }).format(duration)}</InfoRow>
                ) : null}
                <InfoRow label={t("nodeDetail.observed")}>{status?.observed_at ? intl.relative(status.observed_at) : "—"}</InfoRow>
                {status?.last_status_raw ? (
                  <InfoRow label={t("nodeDetail.rawStatus")} mono>{status.last_status_raw}</InfoRow>
                ) : null}
                {status?.last_error ? (
                  <div className="mt-3 rounded-md border border-destructive/20 bg-destructive/5 p-3">
                    <p className="flex items-center gap-1.5 text-xs font-medium text-destructive">
                      <TriangleAlert className="h-3.5 w-3.5" />
                      {t("nodeDetail.lastError")}
                    </p>
                    <p className="mt-1 text-xs text-destructive">
                      {t(`errors.${status.last_error.code}`, {
                        ...status.last_error.params,
                        defaultValue: status.last_error.code,
                      })}
                    </p>
                    <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                      {status.last_error.error_class}
                      {status.last_error.at ? ` · ${intl.dateTime(status.last_error.at)}` : ""}
                    </p>
                  </div>
                ) : status?.status === "failed" ? (
                  <p className="mt-3 rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
                    {t("nodeDetail.noErrorDetail")}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </div>

          {Object.keys(node.vars ?? {}).length ? (
            <Card className="mt-4">
              <CardHeader>
                <CardTitle>{t("nodeForm.variables")}</CardTitle>
                <CardDescription>{t("nodeForm.varsHelp")}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(node.vars ?? {}).map(([key, value]) => (
                    <div key={key} className="bg-card p-3">
                      <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{key}</p>
                      <p className="mt-1 break-all font-mono text-xs">{typeof value === "string" ? value : JSON.stringify(value)}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}
        </TabsContent>

        <TabsContent value="configuration" className="mt-5">
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle>{t("nodeDetail.configTitle")}</CardTitle>
                <CardDescription>{t("nodeDetail.configDescription")}</CardDescription>
              </div>
              <div className="flex gap-2">
                <CopyButton value={configQuery.data ?? ""} />
                <Button variant="outline" size="sm" onClick={() => void api.downloadNode(nodeId)}>
                  <Download />
                  {t("nodeDetail.downloadConfig")}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {configQuery.isLoading ? (
                <div className="h-72 animate-pulse rounded-md bg-muted" />
              ) : configQuery.isError ? (
                <ErrorState onRetry={() => void configQuery.refetch()} compact />
              ) : configQuery.data?.trim() ? (
                <CodeEditor value={configQuery.data} readOnly language="text" minHeight={280} maxHeight={620} />
              ) : (
                <EmptyState icon={Code2} title={t("nodeDetail.configEmpty")} compact />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions" className="mt-5">
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle>{t("nodeDetail.versionsTitle")}</CardTitle>
                <CardDescription>{t("nodeDetail.versionsDescription")}</CardDescription>
              </div>
              {selected.length === 2 ? (
                <Button size="sm" onClick={() => setTab("diff")}>
                  {t("nodeDetail.compareSelected")}
                  <ArrowUpRight />
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {versionsQuery.isLoading ? (
                <div className="space-y-2">
                  {[0, 1, 2].map((item) => <div key={item} className="h-10 animate-pulse rounded bg-muted" />)}
                </div>
              ) : versionsQuery.isError ? (
                <ErrorState onRetry={() => void versionsQuery.refetch()} compact />
              ) : !versionsQuery.data?.available ? (
                <EmptyState
                  icon={CalendarClock}
                  title={t("nodeDetail.noVersions")}
                  description={versionsQuery.data?.reason === "output_unsupported" ? t("nodeDetail.outputUnsupported") : t("nodeDetail.noVersions")}
                  compact
                />
              ) : versions.length === 0 ? (
                <EmptyState icon={CalendarClock} title={t("nodeDetail.noVersions")} compact />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-8" />
                      <TableHead>{t("nodeDetail.version")}</TableHead>
                      <TableHead>{t("nodeDetail.author")}</TableHead>
                      <TableHead className="hidden lg:table-cell">{t("nodeDetail.message")}</TableHead>
                      <TableHead className="text-right">{t("common.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {versions.map((version, index) => (
                      <TableRow key={version.oid}>
                        <TableCell>
                          <Checkbox
                            checked={selected.includes(version.oid)}
                            onCheckedChange={() => toggleVersion(version.oid)}
                            aria-label={t("nodeDetail.selectVersion")}
                          />
                        </TableCell>
                        <TableCell>
                          <button type="button" className="inline-flex items-center gap-2 text-left hover:text-primary" onClick={() => setVersionDialog(version)}>
                            <span className="font-mono text-xs">{version.oid.slice(0, 10)}</span>
                            {index === 0 ? <Badge variant="success">{t("nodeDetail.current")}</Badge> : null}
                          </button>
                        </TableCell>
                        <TableCell className="text-xs">{version.author ?? "—"}</TableCell>
                        <TableCell className="hidden max-w-[26rem] truncate text-xs text-muted-foreground lg:table-cell">
                          {version.message ?? "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <span className="mr-2 self-center font-mono text-[10px] text-muted-foreground">
                              {intl.dateTime(version.time)}
                            </span>
                            <Button variant="ghost" size="icon-xs" onClick={() => setVersionDialog(version)} aria-label={t("nodeDetail.selectVersion")}>
                              <Code2 />
                            </Button>
                            <Button variant="ghost" size="icon-xs" onClick={() => void api.downloadNode(nodeId, version.oid)} aria-label={t("common.download")}>
                              <Download />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="diff" className="mt-5">
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div>
              <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{t("nodeDetail.version")} A</p>
              <CodeSelect
                value={selected[0] ?? ""}
                versions={versions}
                onChange={(oid) => setSelected((current) => [oid, current[1]].filter(Boolean) as string[])}
              />
            </div>
            <span className="pb-2 text-muted-foreground">↔</span>
            <div>
              <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground">{t("nodeDetail.version")} B</p>
              <CodeSelect
                value={selected[1] ?? ""}
                versions={versions}
                onChange={(oid) => setSelected((current) => [current[0], oid].filter(Boolean) as string[])}
              />
            </div>
            <Button variant="outline" size="sm" onClick={() => void diffQuery.refetch()} disabled={selected.length !== 2 || diffQuery.isFetching}>
              {diffQuery.isFetching ? <Spinner /> : <RefreshCw />}
              {t("common.refresh")}
            </Button>
          </div>
          {selected.length !== 2 ? (
            <EmptyState icon={Copy} title={t("nodeDetail.selectTwo")} compact />
          ) : diffQuery.isLoading ? (
            <div className="h-72 animate-pulse rounded-lg bg-muted" />
          ) : diffQuery.isError ? (
            <ErrorState onRetry={() => void diffQuery.refetch()} compact />
          ) : diffQuery.data ? (
            <DiffView
              diff={diffQuery.data}
              fromLabel={selected[0].slice(0, 10)}
              toLabel={selected[1].slice(0, 10)}
            />
          ) : null}
        </TabsContent>
        <TabsContent value="history" className="mt-5">
          <Card>
            <CardHeader>
              <CardTitle>{t("nodeDetail.history")}</CardTitle>
              <CardDescription>
                {historyQuery.data?.success_rate !== null && historyQuery.data?.success_rate !== undefined
                  ? t("nodeDetail.historySummary", {
                      rate: Math.round(historyQuery.data.success_rate * 100),
                      total: historyQuery.data.total,
                    })
                  : t("nodeDetail.historyEmpty")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {historyQuery.isLoading ? (
                <div className="h-24 animate-pulse rounded-md bg-muted" />
              ) : historyQuery.isError ? (
                <ErrorState onRetry={() => void historyQuery.refetch()} compact />
              ) : historyQuery.data?.items.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("nodeDetail.historyStarted")}</TableHead>
                      <TableHead>{t("nodeDetail.status")}</TableHead>
                      <TableHead>{t("nodeDetail.duration")}</TableHead>
                      <TableHead>{t("nodeDetail.trigger")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {historyQuery.data.items.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell className="font-mono text-[11px]">{item.started_at ? intl.dateTime(item.started_at) : "—"}</TableCell>
                        <TableCell><Badge variant={item.status === "success" ? "success" : "destructive"}>{item.status}</Badge></TableCell>
                        <TableCell className="font-mono text-[11px]">{item.duration_seconds ?? "—"} s</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{item.trigger}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <EmptyState icon={CalendarClock} title={t("nodeDetail.historyEmpty")} compact />
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <NodeFormSheet
        open={editOpen}
        onOpenChange={setEditOpen}
        nodeId={nodeId}
        onSaved={() => {
          void queryClient.invalidateQueries({ queryKey: ["node", nodeId] });
          void queryClient.invalidateQueries({ queryKey: ["node-status", nodeId] });
        }}
      />

      <VersionContentDialog nodeId={nodeId} version={versionDialog} onOpenChange={(open) => !open && setVersionDialog(null)} />

      <ConfirmDialog
        open={trustOpen}
        onOpenChange={setTrustOpen}
        destructive={false}
        title={t("nodeDetail.trustHostKeyTitle", { name: node.name })}
        description={t("nodeDetail.trustHostKeyDescription", { address: node.address ?? "—" })}
        confirmLabel={t("nodeDetail.trustHostKeyConfirm")}
        loading={trustHostKey.isPending}
        onConfirm={() => trustHostKey.mutate()}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t("nodes.deleteTitle")}
        description={t("nodeDetail.deleteConfirm", { name: node.name })}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

function CodeSelect({
  value,
  versions,
  onChange,
}: {
  value: string;
  versions: Version[];
  onChange: (oid: string) => void;
}) {
  const { t } = useTranslation();
  const intl = useIntl();
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-8 max-w-[17rem] rounded-md border border-input bg-card px-2 font-mono text-[11px] shadow-xs focus:outline-none focus:ring-2 focus:ring-ring"
      aria-label={t("nodeDetail.version")}
    >
      {versions.map((version) => (
        <option key={version.oid} value={version.oid}>
          {version.oid.slice(0, 10)} · {intl.dateTime(version.time)}
        </option>
      ))}
    </select>
  );
}
