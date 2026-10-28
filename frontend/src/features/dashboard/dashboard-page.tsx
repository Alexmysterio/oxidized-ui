import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowRight, CheckCircle2, Clock3, DatabaseBackup, FileWarning, Gauge, Network, RadioTower, RefreshCw, ShieldCheck, TriangleAlert, X, Zap } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { MetricCard } from "@/components/shared/metric-card";
import { PageHeader } from "@/components/shared/page-header";
import { PageSkeleton, Spinner } from "@/components/shared/loaders";
import { NodeStatusBadge, OxidizedStateBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { JobMeta } from "@/features/jobs/job-ui";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import { formatNumber } from "@/lib/format";

export function DashboardPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can, user } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [confirmAll, setConfirmAll] = useState(false);
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => localStorage.getItem("oxidized-ui:onboarding-dismissed") === "1");
  usePageTitle("nav.dashboard");

  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: 20_000,
  });
  const jobsQuery = useQuery({
    queryKey: ["jobs", "recent"],
    queryFn: () => api.jobs({ page_size: 5 }),
    enabled: can("jobs.read"),
  });
  const failedNodesQuery = useQuery({
    queryKey: ["nodes", "failed-dashboard"],
    queryFn: () => api.nodes({ status: "failed", page_size: 5, sort: "last_backup_at", order: "desc" }),
    enabled: Boolean(statusQuery.data && statusQuery.data.nodes.failed > 0),
  });

  const backupAll = useMutation({
    mutationFn: () => api.backupsAll(),
    onSuccess: () => {
      toast.success(t("dashboard.backupAllQueued"));
      setConfirmAll(false);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const retryNode = useMutation({
    mutationFn: (nodeId: number) => api.backupNode(nodeId),
    onSuccess: () => {
      toast.success(t("dashboard.retryQueued"));
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
      void queryClient.invalidateQueries({ queryKey: ["nodes"] });
    },
    onError: (error) => notifyError(t, error),
  });

  if (statusQuery.isLoading) return <PageSkeleton />;
  if (statusQuery.isError || !statusQuery.data) {
    return <ErrorState onRetry={() => void statusQuery.refetch()} />;
  }

  const status = statusQuery.data;
  const chartData = status.activity.map((point) => ({
    ...point,
    label: new Intl.DateTimeFormat(intl.language, { day: "2-digit", month: "short" }).format(
      new Date(`${point.date}T00:00:00`),
    ),
  }));
  const totalActivity = status.activity.reduce((sum, point) => sum + point.success + point.failed, 0);
  const totalSuccess = status.activity.reduce((sum, point) => sum + point.success, 0);
  const totalFailed = status.activity.reduce((sum, point) => sum + point.failed, 0);
  const isHealthy = status.oxidized.state === "online";
  const stateLabel = t(`status.${status.oxidized.state}`);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={
          <>
            <RadioTower className="h-3.5 w-3.5 text-primary" />
            {t("dashboard.eyebrow")}
          </>
        }
        title={t("dashboard.title")}
        description={t("dashboard.subtitle")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void statusQuery.refetch()} disabled={statusQuery.isFetching}>
              {statusQuery.isFetching ? <Spinner /> : <RefreshCw />}
              {t("dashboard.refreshStatus")}
            </Button>
            {can("backups.trigger") ? (
              <Button size="sm" onClick={() => setConfirmAll(true)} disabled={status.nodes.total === 0 || backupAll.isPending}>
                {backupAll.isPending ? <Spinner /> : <DatabaseBackup />}
                {t("dashboard.forceBackupAll")}
              </Button>
            ) : null}
          </>
        }
      />

      {status.warnings.length ? (
        <div className="flex gap-3 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-sm">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <div className="space-y-1">
            <p className="font-medium text-warning">{t("dashboard.warnings")}</p>
            <div className="space-y-0.5 text-xs text-muted-foreground">
              {status.warnings.map((warning, index) => (
                <p key={`${warning}-${index}`}>{t(`errors.${warning}`, { defaultValue: warning })}</p>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <section className="relative overflow-hidden rounded-xl border border-slate-800/80 bg-[#080e1b] p-5 text-slate-100 shadow-lift sm:p-7">
        <div className="sidebar-grid absolute inset-0 opacity-60" />
        <div className="pointer-events-none absolute -left-24 -top-28 h-72 w-72 rounded-full bg-[#476bff]/20 blur-[90px]" />
        <div
          className={`pointer-events-none absolute -right-20 bottom-0 h-64 w-64 rounded-full blur-[90px] ${
            isHealthy ? "bg-emerald-400/10" : "bg-red-500/10"
          }`}
        />
        <div className="relative grid gap-7 lg:grid-cols-[1.2fr_1fr] lg:items-center">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500">
                {t("dashboard.oxidizedSignal")}
              </span>
              <OxidizedStateBadge state={status.oxidized.state} />
            </div>
            <div className="mt-4 flex items-center gap-4">
              <div className="relative">
                <span className="absolute inset-0 animate-pulse-ring rounded-full bg-primary/20" />
                <span
                  className={`relative flex h-12 w-12 items-center justify-center rounded-full border ${
                    isHealthy
                      ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                      : "border-red-400/30 bg-red-400/10 text-red-300"
                  }`}
                >
                  <RadioTower className="h-5 w-5" />
                </span>
              </div>
              <div>
                <p className="font-mono text-[clamp(1.9rem,3vw,2.8rem)] font-medium uppercase leading-none tracking-[-0.04em]">
                  {stateLabel}
                </p>
                <p className="mt-1.5 text-xs text-slate-400">
                  {status.oxidized.api_online ? t("status.apiOnline") : t("status.apiOffline")}
                  {status.oxidized.container_state ? ` · ${status.oxidized.container_state}` : ""}
                </p>
              </div>
            </div>
            {!isHealthy ? (
              <div className="mt-5 flex flex-col gap-2 rounded-lg border border-red-400/15 bg-red-400/[0.05] p-3 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
                <span>{t("dashboard.systemOfflineDescription")}</span>
                {can("logs.read") ? (
                  <Button
                    size="xs"
                    variant="outline"
                    className="border-white/15 bg-white/5 text-slate-200 hover:bg-white/10 hover:text-white"
                    onClick={() => navigate("/status")}
                  >
                    {t("dashboard.openLogs")}
                    <ArrowRight />
                  </Button>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/[0.07] bg-white/[0.07]">
            {[
              {
                label: t("dashboard.apiLabel"),
                value: status.oxidized.api_online ? t("status.apiOnline") : t("status.apiOffline"),
                sub: status.oxidized.last_seen_at ? intl.relative(status.oxidized.last_seen_at) : "—",
              },
              {
                label: t("dashboard.containerLabel"),
                value: status.oxidized.container_running ? t("status.running") : t("status.stopped"),
                sub: status.oxidized.health ?? status.oxidized.container_state ?? "—",
              },
              {
                label: t("dashboard.lastBackupLabel"),
                value: status.backups.last_success_at ? intl.relative(status.backups.last_success_at) : t("status.neverBackedUp"),
                sub: status.backups.last_failure_at
                  ? `${t("status.lastFailure")}: ${intl.relative(status.backups.last_failure_at)}`
                  : t("status.lastFailure") + ": —",
              },
              {
                label: t("status.activeJobs"),
                value: formatNumber(status.backups.active_jobs, intl.language),
                sub: status.backups.active_jobs > 0 ? t("jobs.running") : t("dashboard.noActiveJobs"),
              },
            ].map((item) => (
              <div key={item.label} className="bg-[#080e1b]/90 p-3.5">
                <p className="font-mono text-[8px] uppercase tracking-[0.18em] text-slate-500">{item.label}</p>
                <p className="mt-1.5 truncate text-sm font-medium text-slate-100">{item.value}</p>
                <p className="mt-0.5 truncate font-mono text-[9px] text-slate-500">{item.sub}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2 sm:gap-3 xl:grid-cols-4">
        <MetricCard
          label={t("dashboard.nodesTotal")}
          value={formatNumber(status.nodes.total, intl.language)}
          icon={Network}
          hint={t("dashboard.nodesHint")}
          onClick={() => navigate("/nodes")}
        />
        <MetricCard
          label={t("dashboard.ok")}
          value={formatNumber(status.nodes.ok, intl.language)}
          icon={CheckCircle2}
          tone="success"
          hint={t("nodeStatus.ok")}
          onClick={() => navigate("/nodes?status=ok")}
        />
        <MetricCard
          label={t("dashboard.failedNodes")}
          value={formatNumber(status.nodes.failed, intl.language)}
          icon={TriangleAlert}
          tone="destructive"
          hint={t("nodeStatus.failed")}
          onClick={() => navigate("/nodes?status=failed")}
        />
        <MetricCard
          label={t("dashboard.pending")}
          value={formatNumber(status.nodes.pending + status.nodes.never, intl.language)}
          icon={Clock3}
          tone="warning"
          hint={`${formatNumber(status.nodes.pending, intl.language)} ${t("dashboard.pending").toLowerCase()} · ${formatNumber(status.nodes.never, intl.language)} ${t("dashboard.never").toLowerCase()}`}
          onClick={() => navigate("/nodes")}
        />
      </section>

      {status.sla.groups.length ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.sla")}</CardTitle>
            <CardDescription>{t("dashboard.slaDescription", { days: status.sla.days })}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {status.sla.groups.map((item) => (
                <div key={item.group} className="rounded-lg border bg-muted/15 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs">{item.group}</span>
                    <span className="text-sm font-semibold">{item.rate === null ? "—" : `${Math.round(item.rate * 100)}%`}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                    <div className="h-full rounded-full bg-success" style={{ width: `${Math.round((item.rate ?? 0) * 100)}%` }} />
                  </div>
                  <p className="mt-2 text-[10px] text-muted-foreground">{t("dashboard.slaCounts", { success: item.success, failed: item.failed })}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {!onboardingDismissed && status.nodes.total > 0 && !status.backups.last_success_at ? (
        <Card className="border-primary/25 bg-primary/[0.035]">
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle>{t("dashboard.onboarding")}</CardTitle>
              <CardDescription>{t("dashboard.onboardingDescription")}</CardDescription>
            </div>
            <Button variant="ghost" size="icon-sm" onClick={() => { localStorage.setItem("oxidized-ui:onboarding-dismissed", "1"); setOnboardingDismissed(true); }} aria-label={t("common.dismiss")}>
              <X />
            </Button>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <Button asChild variant="outline" className="justify-start"><Link to="/nodes"><CheckCircle2 />{t("dashboard.onboardingNodes")}</Link></Button>
            <Button asChild variant="outline" className="justify-start"><Link to="/nodes"><ShieldCheck />{t("dashboard.onboardingTest")}</Link></Button>
            <Button variant="outline" className="justify-start" disabled={!can("backups.trigger")} onClick={() => setConfirmAll(true)}><DatabaseBackup />{t("dashboard.onboardingBackup")}</Button>
            <Button asChild variant="outline" className="justify-start"><Link to="/system"><RadioTower />{t("dashboard.onboardingNotify")}</Link></Button>
          </CardContent>
        </Card>
      ) : null}

      {status.nodes.total === 0 ? (
        <EmptyState
          icon={Network}
          title={t("dashboard.noNodesTitle")}
          description={t("dashboard.noNodesDescription")}
          action={
            user?.role !== "viewer" ? (
              <Button asChild>
                <Link to="/nodes">
                  <Zap />
                  {t("dashboard.addFirstNode")}
                </Link>
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <section className={can("jobs.read") ? "grid gap-4 xl:grid-cols-[1.55fr_0.85fr]" : "grid gap-4"}>
            <Card>
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div>
                  <CardTitle>{t("dashboard.activity")}</CardTitle>
                  <CardDescription>{t("dashboard.activityDescription")}</CardDescription>
                </div>
                <div className="flex items-center gap-3 pt-0.5">
                  <span className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-sm bg-emerald-500" />
                    {t("dashboard.success")}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <span className="h-1.5 w-1.5 rounded-sm bg-red-500" />
                    {t("dashboard.failed")}
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <div
                  role="img"
                  aria-label={t("dashboard.activitySummary", { success: totalSuccess, failed: totalFailed })}
                  className="relative h-[248px] w-full"
                >
                  {totalActivity === 0 ? (
                    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-card/70 text-center backdrop-blur-[1px]">
                      <Activity className="mb-2 h-5 w-5 text-muted-foreground/50" />
                      <p className="text-xs font-medium">{t("dashboard.noActivity")}</p>
                      <p className="mt-1 max-w-xs text-[11px] text-muted-foreground">{t("dashboard.noActivityDescription")}</p>
                    </div>
                  ) : null}
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} barGap={4} margin={{ top: 8, right: 4, left: -22, bottom: 0 }}>
                      <CartesianGrid vertical={false} stroke="hsl(var(--border))" strokeDasharray="2 4" />
                      <XAxis
                        dataKey="label"
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 9, fontFamily: "JetBrains Mono Variable", fill: "hsl(var(--muted-foreground))" }}
                        minTickGap={42}
                      />
                      <YAxis
                        allowDecimals={false}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 9, fontFamily: "JetBrains Mono Variable", fill: "hsl(var(--muted-foreground))" }}
                      />
                      <Tooltip
                        cursor={{ fill: "hsl(var(--muted) / .5)" }}
                        contentStyle={{
                          background: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 11,
                          color: "hsl(var(--popover-foreground))",
                          boxShadow: "var(--tw-shadow)",
                        }}
                      />
                      <Bar dataKey="success" name={t("dashboard.success")} stackId="a" fill="#22a06b" maxBarSize={18} />
                      <Bar dataKey="failed" name={t("dashboard.failed")} stackId="a" fill="#e05252" maxBarSize={18} radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>

            {can("jobs.read") ? (
              <Card>
                <CardHeader className="flex-row items-start justify-between space-y-0">
                  <div>
                    <CardTitle>{t("dashboard.recentJobs")}</CardTitle>
                    <CardDescription>{t("dashboard.recentJobsDescription")}</CardDescription>
                  </div>
                  {can("logs.read") ? (
                    <Button variant="ghost" size="icon-sm" asChild aria-label={t("common.viewAll")} title={t("common.viewAll")}>
                      <Link to="/status">
                        <ArrowRight />
                      </Link>
                    </Button>
                  ) : null}
                </CardHeader>
                <CardContent className="space-y-1">
                  {jobsQuery.isLoading ? (
                    <div className="space-y-3 py-2">
                      {[0, 1, 2].map((item) => (
                        <div key={item} className="h-12 animate-pulse rounded-md bg-muted" />
                      ))}
                    </div>
                  ) : jobsQuery.data?.items.length ? (
                    jobsQuery.data.items.slice(0, 4).map((job) => (
                      <div key={job.id} className="border-b border-border/60 py-2.5 last:border-0">
                        <JobMeta job={job} compact />
                      </div>
                    ))
                  ) : (
                    <p className="py-8 text-center text-xs text-muted-foreground">{t("dashboard.noJobs")}</p>
                  )}
                </CardContent>
              </Card>
            ) : null}
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.55fr_0.85fr]">
            <Card>
              <CardHeader className="flex-row items-start justify-between space-y-0">
                <div>
                  <CardTitle>{t("dashboard.failedNodesTitle")}</CardTitle>
                  <CardDescription>{t("dashboard.failedNodesDescription")}</CardDescription>
                </div>
                <Button variant="ghost" size="sm" asChild>
                  <Link to="/nodes?status=failed">{t("common.viewAll")}</Link>
                </Button>
              </CardHeader>
              <CardContent>
                {failedNodesQuery.isLoading ? (
                  <div className="space-y-2">
                    <div className="h-10 animate-pulse rounded bg-muted" />
                    <div className="h-10 animate-pulse rounded bg-muted" />
                  </div>
                ) : failedNodesQuery.data?.items.length ? (
                  <div className="divide-y divide-border/60">
                    {failedNodesQuery.data.items.map((node) => (
                      <Link
                        key={node.id}
                        to={`/nodes/${node.id}`}
                        className="flex items-center gap-3 py-2.5 transition-colors hover:text-primary"
                      >
                        <span className="flex h-8 w-8 items-center justify-center rounded-md border bg-card">
                          <FileWarning className="h-3.5 w-3.5 text-destructive" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{node.name}</span>
                          <span className="block truncate font-mono text-[10px] text-muted-foreground">
                            {node.address ?? "-"} · {node.model}
                            {node.last_status_raw ? ` · ${t(`nodeStatus.${node.last_status_raw}`)}` : ""}
                          </span>
                        </span>
                        <NodeStatusBadge status={node.status} />
                        <span className="hidden font-mono text-[10px] text-muted-foreground sm:block">
                          {node.last_attempt_at ? intl.relative(node.last_attempt_at) : "-"}
                        </span>
                        {can("backups.trigger") ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            className="shrink-0"
                            disabled={retryNode.isPending}
                            onClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              retryNode.mutate(node.id);
                            }}
                            aria-label={t("dashboard.retry")}
                            title={t("dashboard.retry")}
                          >
                            <RefreshCw />
                          </Button>
                        ) : null}
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                    <ShieldCheck className="h-4 w-4 text-success" />
                    {t("dashboard.noFailedNodes")}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="relative overflow-hidden">
              <div className="pointer-events-none absolute inset-0 opacity-[0.55] [background-image:radial-gradient(circle_at_80%_0%,hsl(var(--primary)/.11),transparent_60%)]" />
              <CardHeader>
                <CardTitle>{t("dashboard.lastBackupLabel")}</CardTitle>
                <CardDescription>{t("status.lastSeen")}</CardDescription>
              </CardHeader>
              <CardContent className="relative space-y-4">
                <div>
                  <p className="metric-number text-2xl">
                    {status.backups.last_success_at ? intl.relative(status.backups.last_success_at) : t("status.neverBackedUp")}
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                    {status.backups.last_success_at ? intl.dateTime(status.backups.last_success_at) : "—"}
                  </p>
                </div>
                <div className="h-px bg-border" />
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t("status.lastFailure")}</span>
                  <span className="font-mono text-[10px]">{status.backups.last_failure_at ? intl.relative(status.backups.last_failure_at) : "—"}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{t("status.apiOnline")}</span>
                  <span className="font-mono text-[10px]">{status.oxidized.last_seen_at ? intl.relative(status.oxidized.last_seen_at) : "—"}</span>
                </div>
                <Button variant="outline" className="w-full" asChild>
                  <Link to="/nodes">
                    <Gauge />
                    {t("nav.nodes")}
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </section>
        </>
      )}

      <ConfirmDialog
        open={confirmAll}
        onOpenChange={setConfirmAll}
        title={t("dashboard.backupAllConfirmTitle")}
        description={t("dashboard.backupAllConfirmDescription", { count: status.nodes.total })}
        confirmLabel={t("dashboard.forceBackupAll")}
        destructive={false}
        loading={backupAll.isPending}
        onConfirm={() => backupAll.mutate()}
      />
    </div>
  );
}
