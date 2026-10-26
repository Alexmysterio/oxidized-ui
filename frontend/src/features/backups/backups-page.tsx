import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";

export function BackupsPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [scheduleGroup, setScheduleGroup] = useState("");
  const [scheduleInterval, setScheduleInterval] = useState(1440);
  usePageTitle("nav.backups");

  const schedulesQuery = useQuery({
    queryKey: ["backup-schedules"],
    queryFn: api.backupSchedules,
    enabled: can("backups.trigger"),
  });

  const createSchedule = useMutation({
    mutationFn: () => api.createBackupSchedule(scheduleGroup.trim() || null, scheduleInterval),
    onSuccess: () => {
      toast.success(t("logs.scheduleCreated"));
      setScheduleGroup("");
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
          <p className="rounded-md border border-border/70 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
            {t("backups.howItWorks")}
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label>{t("logs.scheduleGroup")}</Label>
              <Input
                value={scheduleGroup}
                onChange={(event) => setScheduleGroup(event.target.value)}
                placeholder={t("logs.scheduleAllGroups")}
                className="w-52"
              />
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
            <Button type="button" size="sm" onClick={() => createSchedule.mutate()} disabled={createSchedule.isPending || scheduleInterval < 15}>
              {createSchedule.isPending ? <Spinner /> : <CalendarClock />}
              {t("logs.scheduleCreate")}
            </Button>
          </div>
          <div className="divide-y">
            {(schedulesQuery.data?.items ?? []).map((schedule) => (
              <div key={schedule.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                <span className="font-mono">
                  {schedule.group_name ?? t("logs.scheduleAllGroups")} · {schedule.interval_minutes} min ·{" "}
                  {schedule.next_run_at ? intl.dateTime(schedule.next_run_at) : "-"}
                </span>
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
            {(schedulesQuery.data?.items ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("logs.noSchedules")}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
