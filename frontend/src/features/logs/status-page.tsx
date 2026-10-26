import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownToLine,
  CircleDot,
  Download,
  Pause,
  Play,
  RadioTower,
  RefreshCw,
  RotateCcw,
  Search,
  ServerCog,
  Square,
  Terminal,
  Trash2,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { OxidizedStateBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { JobMeta } from "@/features/jobs/job-ui";
import { useLogStream } from "@/features/logs/use-log-stream";
import { useDebounce } from "@/hooks/use-debounce";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorCodeMessage, notifyError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { LogLine } from "@/types/api";

const levelColor: Record<string, string> = {
  trace: "text-slate-500",
  debug: "text-sky-400",
  info: "text-emerald-400",
  warn: "text-amber-400",
  error: "text-red-400",
  fatal: "text-red-300",
  unknown: "text-slate-400",
};

function LogConsoleLine({ line, language, timeZone }: { line: LogLine; language: string; timeZone?: string }) {
  const time = line.timestamp
    ? new Intl.DateTimeFormat(language, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        ...(timeZone ? { timeZone } : {}),
      }).format(new Date(line.timestamp))
    : "";
  return (
    <div className="grid grid-cols-[4.5rem_3.5rem_minmax(0,1fr)] gap-2 border-b border-white/[0.035] px-3 py-1 hover:bg-white/[0.025]">
      <span className="select-none font-mono text-[10px] tabular-nums text-slate-600">{time}</span>
      <span className={cn("select-none font-mono text-[9px] font-medium uppercase tracking-wide", levelColor[line.level] ?? levelColor.unknown)}>
        {line.level}
      </span>
      <span className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-slate-300">{line.text}</span>
    </div>
  );
}

export function StatusPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { user, can } = useAuth();
  const queryClient = useQueryClient();
  const [level, setLevel] = useState("info");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 350);
  const [tail, setTail] = useState(500);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [restartOpen, setRestartOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  usePageTitle("logs.title");

  const stream = useLogStream({ level, query: debouncedSearch, tail, paused });
  const statusQuery = useQuery({ queryKey: ["status"], queryFn: api.status, refetchInterval: 15_000 });
  const jobsQuery = useQuery({
    queryKey: ["jobs", "status-page"],
    queryFn: () => api.jobs({ page_size: 20 }),
    refetchInterval: 4_000,
  });

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [stream.lines, autoScroll]);

  useEffect(() => {
    if (stream.streamError) {
      toast.error(t("logs.streamError"), {
        description: t(`errors.${stream.streamError}`, { defaultValue: stream.streamError }),
      });
    }
  }, [stream.streamError, t]);

  const reload = useMutation({
    mutationFn: api.reloadOxidized,
    onSuccess: () => {
      toast.success(t("logs.reloadDone"));
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const cancelJob = useMutation({
    mutationFn: (id: number) => api.cancelJob(id),
    onSuccess: () => {
      toast.success(t("logs.jobCancelled"));
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const restart = useMutation({
    mutationFn: api.restartOxidized,
    onSuccess: (job) => {
      setRestartOpen(false);
      toast.success(t("logs.restartDone"), { description: `#${job.id}` });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const status = statusQuery.data;
  const statusTone: "success" | "warning" | "destructive" =
    stream.status === "connected" ? "success" : stream.status === "paused" ? "warning" : "destructive";

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Terminal className="h-3.5 w-3.5 text-primary" />
            {t("nav.operations")}
          </>
        }
        title={t("logs.title")}
        description={t("logs.subtitle")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void api.downloadLogs({ level: level === "__all__" ? undefined : level, q: debouncedSearch || undefined }).catch((error) => notifyError(t, error))}>
              <Download />
              {t("logs.download")}
            </Button>
            {can("nodes.write") ? (
              <Button variant="outline" size="sm" onClick={() => reload.mutate()} disabled={reload.isPending}>
                {reload.isPending ? <Spinner /> : <RefreshCw />}
                {t("logs.reloadNodes")}
              </Button>
            ) : null}
            {user?.role === "admin" ? (
              <Button variant="destructive-outline" size="sm" onClick={() => setRestartOpen(true)}>
                <RotateCcw />
                {t("logs.restartOxidized")}
              </Button>
            ) : null}
          </>
        }
      />

      {statusQuery.isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((item) => <div key={item} className="h-24 animate-pulse rounded-lg bg-muted" />)}
        </div>
      ) : statusQuery.isError || !status ? (
        <ErrorState onRetry={() => void statusQuery.refetch()} compact />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div className="relative overflow-hidden rounded-lg border bg-card p-4 shadow-soft">
            <div className="flex items-center justify-between">
              <p className="network-label text-[9px]">{t("dashboard.oxidizedSignal")}</p>
              <RadioTower className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <div className="mt-3"><OxidizedStateBadge state={status.oxidized.state} /></div>
            <p className="mt-2 font-mono text-[9px] text-muted-foreground">{status.oxidized.last_seen_at ? intl.relative(status.oxidized.last_seen_at) : "—"}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 shadow-soft">
            <div className="flex items-center justify-between">
              <p className="network-label text-[9px]">{t("dashboard.apiLabel")}</p>
              <CircleDot className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <p className={cn("mt-3 text-sm font-medium", status.oxidized.api_online ? "text-success" : "text-destructive")}>
              {status.oxidized.api_online ? t("status.apiOnline") : t("status.apiOffline")}
            </p>
            <p className="mt-2 font-mono text-[9px] text-muted-foreground">{t("status.lastSeen")}: {status.oxidized.last_seen_at ? intl.relative(status.oxidized.last_seen_at) : "—"}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 shadow-soft">
            <div className="flex items-center justify-between">
              <p className="network-label text-[9px]">{t("dashboard.containerLabel")}</p>
              <ServerCog className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <p className={cn("mt-3 text-sm font-medium", status.oxidized.container_running ? "text-success" : "text-destructive")}>
              {status.oxidized.container_running ? t("status.running") : t("status.stopped")}
            </p>
            <p className="mt-2 truncate font-mono text-[9px] text-muted-foreground">{status.oxidized.container_state ?? "—"} · {status.oxidized.health ?? "—"}</p>
          </div>
          <div className="rounded-lg border bg-card p-4 shadow-soft">
            <div className="flex items-center justify-between">
              <p className="network-label text-[9px]">{t("status.activeJobs")}</p>
              <Activity className="h-3.5 w-3.5 text-muted-foreground" />
            </div>
            <p className="mt-3 text-sm font-medium">{intl.number(status.backups.active_jobs)}</p>
            <p className="mt-2 font-mono text-[9px] text-muted-foreground">{t("logs.queueTitle")}</p>
          </div>
        </div>
      )}

      {status?.warnings.length ? (
        <div className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" />
          <div className="space-y-0.5">
            {status.warnings.map((warning, index) => (
              <p key={`${warning}-${index}`}>{t(`errors.${warning}`, { defaultValue: warning })}</p>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_25rem]">
        <Card className="overflow-hidden">
          <CardHeader className="gap-3 border-b bg-muted/20 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Terminal className="h-4 w-4 text-primary" />
                {t("logs.live")}
              </CardTitle>
              <Badge variant={statusTone} className="normal-case tracking-normal">
                {stream.status === "connected" ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" /> : null}
                {t(`logs.${stream.status}`)}
              </Badge>
              <span className="font-mono text-[9px] text-muted-foreground">{t("logs.lines", { count: stream.lines.length })}</span>
              <div className="ml-auto flex flex-wrap items-center gap-1">
                <Button variant="ghost" size="icon-sm" onClick={() => setPaused((value) => !value)} aria-label={paused ? t("logs.resume") : t("logs.pause")} title={paused ? t("logs.resume") : t("logs.pause")}>
                  {paused ? <Play /> : <Pause />}
                </Button>
                <Button variant="ghost" size="icon-sm" onClick={stream.clear} aria-label={t("logs.clear")} title={t("logs.clear")}>
                  <Trash2 />
                </Button>
                <Button variant="ghost" size="icon-sm" onClick={() => setAutoScroll((value) => !value)} aria-label={t("logs.autoScroll")} title={t("logs.autoScroll")} className={cn(autoScroll && "text-primary")}>
                  <ArrowDownToLine />
                </Button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-[12rem] flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("logs.searchPlaceholder")} className="h-8 bg-card pl-8 text-xs" />
              </div>
              <Select value={level} onValueChange={setLevel}>
                <SelectTrigger className="h-8 w-[8.5rem] bg-card text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("logs.allLevels")}</SelectItem>
                  {["trace", "debug", "info", "warn", "error", "fatal"].map((value) => (
                    <SelectItem key={value} value={value}>{value}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={String(tail)} onValueChange={(value) => setTail(Number(value))}>
                <SelectTrigger className="h-8 w-[9.5rem] bg-card text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[200, 500, 1000, 2000].map((value) => (
                    <SelectItem key={value} value={String(value)}>{t("logs.tail")}: {value}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <div className="relative">
            <div className="flex items-center justify-between border-b bg-[#070c15] px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-slate-600">
              <span className="inline-flex items-center gap-1.5">
                <Square className="h-2 w-2 fill-current" />
                docker · stdout/stderr
              </span>
              <span>{t("logs.filteredLive")}</span>
            </div>
            <div ref={scrollRef} className="h-[520px] overflow-auto bg-[#070c15] py-1">
              {paused && stream.lines.length === 0 ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-500">{t("logs.paused")}</div>
              ) : stream.lines.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
                  {stream.status === "disconnected" ? <WifiOff className="h-5 w-5 text-slate-600" /> : <Terminal className="h-5 w-5 text-slate-600" />}
                  <p className="text-xs text-slate-400">{t("logs.noLogs")}</p>
                  <p className="max-w-sm text-[10px] leading-relaxed text-slate-600">{t("logs.noLogsDescription")}</p>
                </div>
              ) : (
                stream.lines.map((line) => <LogConsoleLine key={`${line.seq}-${line.timestamp}`} line={line} language={intl.language} timeZone={intl.timeZone} />)
              )}
            </div>
            {stream.streamError ? (
              <div className="flex items-center gap-2 border-t border-red-500/20 bg-red-500/[0.06] px-3 py-2 text-[11px] text-red-300">
                <TriangleAlert className="h-3.5 w-3.5" />
                {errorCodeMessage(t, stream.streamError)}
              </div>
            ) : null}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b bg-muted/20 py-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Activity className="h-4 w-4 text-primary" />
              {t("logs.jobs")}
            </CardTitle>
            <CardDescription>{t("logs.jobsDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="max-h-[580px] space-y-1 overflow-y-auto p-2">
            {jobsQuery.isLoading ? (
              <div className="space-y-2 p-2">
                {[0, 1, 2, 3].map((item) => <div key={item} className="h-16 animate-pulse rounded-md bg-muted" />)}
              </div>
            ) : jobsQuery.isError ? (
              <ErrorState onRetry={() => void jobsQuery.refetch()} compact />
            ) : jobsQuery.data?.items.length ? (
              jobsQuery.data.items.map((job) => (
                <div key={job.id} className="flex items-start justify-between gap-2 rounded-md border border-transparent px-2 py-2.5 hover:border-border hover:bg-muted/30">
                  <JobMeta job={job} compact />
                  {job.status === "queued" || job.status === "running" ? (
                    <Button type="button" variant="ghost" size="sm" className="shrink-0 text-muted-foreground hover:text-destructive" onClick={() => cancelJob.mutate(job.id)}>
                      <Square />
                      {t("logs.cancelJob")}
                    </Button>
                  ) : null}
                </div>
              ))
            ) : (
              <EmptyState icon={Activity} title={t("logs.noJobs")} compact />
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={restartOpen}
        onOpenChange={setRestartOpen}
        title={t("logs.restartConfirmTitle")}
        description={t("logs.restartConfirmDescription")}
        confirmLabel={t("logs.restartOxidized")}
        loading={restart.isPending}
        onConfirm={() => restart.mutate()}
      />
    </div>
  );
}
