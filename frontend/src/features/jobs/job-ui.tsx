import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { useIntl } from "@/hooks/use-app";
import { errorCodeMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { Job, JobStatus } from "@/types/api";

const jobVariants: Record<JobStatus, "secondary" | "info" | "success" | "destructive" | "outline"> = {
  queued: "secondary",
  running: "info",
  succeeded: "success",
  failed: "destructive",
  cancelled: "outline",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation();
  return (
    <Badge variant={jobVariants[status]} className="normal-case tracking-normal">
      {status === "running" ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" /> : null}
      {t(`jobs.${status}`)}
    </Badge>
  );
}

export function jobKindLabel(t: ReturnType<typeof useTranslation>["t"], kind: string): string {
  return t(`jobs.${kind}`, { defaultValue: kind });
}

export function JobMeta({ job, compact = false }: { job: Job; compact?: boolean }) {
  const { t } = useTranslation();
  const intl = useIntl();
  const total = Math.max(job.progress.total, 0);
  const done = Math.min(job.progress.done, total || job.progress.done);
  const percent = total > 0 ? Math.round((done / total) * 100) : job.status === "succeeded" ? 100 : 0;
  return (
    <div className={cn("min-w-0 space-y-1", compact && "space-y-0.5")}>
      <div className="flex flex-wrap items-center gap-2">
        <JobStatusBadge status={job.status} />
        <span className="text-xs font-medium">{jobKindLabel(t, job.kind)}</span>
        {job.node_id ? (
          <span className="font-mono text-[10px] text-muted-foreground">#{job.node_id}</span>
        ) : null}
      </div>
      {job.status === "running" && total > 0 ? (
        <div className="flex items-center gap-2">
          <div className="h-1 w-28 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${percent}%` }} />
          </div>
          <span className="font-mono text-[9px] tabular-nums text-muted-foreground">
            {t("logs.jobProgress", { done, total })}
          </span>
        </div>
      ) : null}
      {job.error ? (
        <p className="line-clamp-2 text-[11px] text-destructive">
          {errorCodeMessage(t, job.error.code, job.error.params)}
        </p>
      ) : null}
      <p className="font-mono text-[9px] text-muted-foreground">
        {intl.relative(job.created_at)}
        {job.created_by ? ` · ${job.created_by.username}` : ""}
      </p>
    </div>
  );
}
