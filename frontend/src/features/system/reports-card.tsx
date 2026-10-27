import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Spinner } from "@/components/shared/loaders";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useIntl } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { notifyError } from "@/lib/errors";

const WEEKDAYS = ["0", "1", "2", "3", "4", "5", "6"];

export function ReportsCard() {
  const { t } = useTranslation();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const [enabled, setEnabled] = useState(false);
  const [weekday, setWeekday] = useState("0");
  const [hour, setHour] = useState(8);

  const settingsQuery = useQuery({ queryKey: ["system-settings"], queryFn: api.systemSettings });
  const reportsQuery = useQuery({ queryKey: ["system-reports"], queryFn: api.reports });

  useEffect(() => {
    if (!settingsQuery.data) return;
    setEnabled(settingsQuery.data.report_enabled);
    setWeekday(String(settingsQuery.data.report_weekday));
    setHour(settingsQuery.data.report_hour);
  }, [settingsQuery.data]);

  const save = useMutation({
    mutationFn: () =>
      api.updateSystemSettings({
        report_enabled: enabled,
        report_weekday: Number(weekday),
        report_hour: hour,
      }),
    onSuccess: () => {
      toast.success(t("reports.saved"));
      void queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const run = useMutation({
    mutationFn: () => api.runReport(),
    onSuccess: () => {
      toast.success(t("reports.queued"));
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      window.setTimeout(() => void reportsQuery.refetch(), 1500);
    },
    onError: (error) => notifyError(t, error),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileSpreadsheet className="h-4 w-4 text-primary" />
          {t("reports.title")}
        </CardTitle>
        <CardDescription>{t("reports.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-xs">
          <Switch checked={enabled} onCheckedChange={setEnabled} />
          {t("reports.enabled")}
        </label>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label>{t("reports.weekday")}</Label>
            <Select value={weekday} onValueChange={setWeekday}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                {WEEKDAYS.map((value) => (
                  <SelectItem key={value} value={value}>{t(`reports.weekdays.${value}`)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>{t("reports.hour")}</Label>
            <Input
              type="number"
              min={0}
              max={23}
              value={hour}
              onChange={(event) => setHour(Number(event.target.value))}
              className="w-24"
            />
          </div>
          <Button type="button" size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? <Spinner /> : null}
            {t("common.save")}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? <Spinner /> : <Play />}
            {t("reports.runNow")}
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">{t("reports.help")}</p>

        <div className="space-y-1 border-t pt-3">
          <p className="text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{t("reports.history")}</p>
          {(reportsQuery.data?.items ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("reports.empty")}</p>
          ) : (
            (reportsQuery.data?.items ?? []).map((item) => (
              <div key={item.filename} className="flex items-center justify-between gap-2 py-1 text-xs">
                <span className="min-w-0 truncate font-mono text-[10px]">{item.filename}</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {item.created_at ? intl.dateTime(item.created_at) : "—"} · {(item.bytes / 1024).toFixed(1)} KB
                  </span>
                  <Button variant="ghost" size="icon-xs" title={t("common.download")} onClick={() => void api.downloadReport(item.filename)}>
                    <Download />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
