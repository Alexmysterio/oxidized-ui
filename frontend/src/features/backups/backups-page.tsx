import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Info, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";

const ALL_GROUPS = "__all__";

function cadenceValue(minutes: number): string {
  if (minutes > 0 && minutes % 1440 === 0) return `${minutes / 1440} d`;
  if (minutes > 0 && minutes % 60 === 0) return `${minutes / 60} h`;
  return `${minutes} min`;
}

export function BackupsPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [scheduleGroup, setScheduleGroup] = useState(ALL_GROUPS);
  const [scheduleInterval, setScheduleInterval] = useState(1440);
  usePageTitle("nav.backups");

  const schedulesQuery = useQuery({
    queryKey: ["backup-schedules"],
    queryFn: api.backupSchedules,
    enabled: can("backups.trigger"),
  });

  const schedules = schedulesQuery.data;
  const oxidizedMinutes = schedules?.oxidized_interval_seconds
    ? Math.round(schedules.oxidized_interval_seconds / 60)
    : null;
  const selectedGroup = (schedules?.groups ?? []).find((group) => group.name === scheduleGroup);
  const selectedCount = selectedGroup ? selectedGroup.node_count : (schedules?.total_nodes ?? 0);
  const redundant = oxidizedMinutes !== null && scheduleInterval >= oxidizedMinutes;

  const createSchedule = useMutation({
    mutationFn: () => api.createBackupSchedule(scheduleGroup === ALL_GROUPS ? null : scheduleGroup, scheduleInterval),
    onSuccess: () => {
      toast.success(t("logs.scheduleCreated"));
      setScheduleGroup(ALL_GROUPS);
      void queryClient.invalidateQueries({ queryKey: ["backup-schedules"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const deleteSchedule = useMutation({
    mutationFn: (id: number) => api.deleteBackupSchedule(id),
    onSuccess: () => {
      toast.success(t("logs.scheduleDeleted"));
      void queryClient.invalidateQueries({ queryKey: ["backup-schedules"] });
    },
    onError: (error) => notifyError(t, error),
  });

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><CalendarClock className="h-3.5 w-3.5 text-primary" />{t("nav.operations")}</>}
        title={t("nav.backups")}
        description={t("backups.subtitle")}
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <CalendarClock className="h-4 w-4 text-primary" />
            {t("logs.backupSchedules")}
          </CardTitle>
          <CardDescription>{t("logs.backupSchedulesDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2 rounded-md border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
            <p>{t("backups.howItWorks")}</p>
            {oxidizedMinutes !== null ? (
              <p className="flex items-start gap-2">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                {t("backups.oxidizedCadence", { value: cadenceValue(oxidizedMinutes) })}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label>{t("logs.scheduleGroup")}</Label>
              <Select value={scheduleGroup} onValueChange={setScheduleGroup}>
                <SelectTrigger className="w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_GROUPS}>
                    {t("logs.scheduleAllGroups")} · {schedules?.total_nodes ?? 0}
                  </SelectItem>
                  {(schedules?.groups ?? []).map((group) => (
                    <SelectItem key={group.name} value={group.name}>
                      {group.name} · {group.node_count}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>{t("logs.scheduleInterval")}</Label>
              <Input
                type="number"
                min={15}
                max={10080}
                value={scheduleInterval}
                onChange={(event) => setScheduleInterval(Number(event.target.value))}
                className="w-36"
              />
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => createSchedule.mutate()}
              disabled={createSchedule.isPending || scheduleInterval < 15 || selectedCount === 0}
            >
              {createSchedule.isPending ? <Spinner /> : <CalendarClock />}
              {t("logs.scheduleCreate")}
            </Button>
          </div>

          <p className={`flex items-start gap-2 rounded-md border p-3 text-xs leading-relaxed ${redundant || selectedCount === 0 ? "border-warning/40 bg-warning/5 text-warning" : "border-border/70 bg-muted/10 text-muted-foreground"}`}>
            {redundant || selectedCount === 0 ? (
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            ) : (
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            )}
            {selectedCount === 0
              ? t("backups.emptyScope")
              : redundant
                ? t("backups.scheduleRedundant", { value: cadenceValue(oxidizedMinutes ?? 0) })
                : t("backups.scheduleUseful", {
                    nodes: selectedCount,
                    value: cadenceValue(scheduleInterval),
                  })}
          </p>

          <div className="divide-y">
            {(schedules?.items ?? []).map((schedule) => (
              <div key={schedule.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                <div className="min-w-0 space-y-0.5">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {schedule.group_name ?? t("logs.scheduleAllGroups")}
                    </span>
                    <span className="text-muted-foreground">
                      {t("backups.nodesCount", { count: schedule.node_count })}
                    </span>
                    <span className="rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 font-mono text-[10px]">
                      {t("backups.everyCadence", { value: cadenceValue(schedule.interval_minutes) })}
                    </span>
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {t("backups.lastRun", { value: schedule.last_run_at ? intl.dateTime(schedule.last_run_at) : t("backups.never") })}
                    {" · "}
                    {t("backups.nextRun", { value: schedule.next_run_at ? intl.dateTime(schedule.next_run_at) : "—" })}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => deleteSchedule.mutate(schedule.id)}
                >
                  <Trash2 />
                  {t("common.delete")}
                </Button>
              </div>
            ))}
            {(schedules?.items ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("logs.noSchedules")}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
