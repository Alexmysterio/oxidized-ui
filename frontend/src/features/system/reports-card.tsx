import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Mail, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
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
  const [keep, setKeep] = useState(12);
  const [emailTo, setEmailTo] = useState("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(587);
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpFrom, setSmtpFrom] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [smtpTls, setSmtpTls] = useState(true);
  const [smtpSsl, setSmtpSsl] = useState(false);

  const settingsQuery = useQuery({ queryKey: ["system-settings"], queryFn: api.systemSettings });
  const reportsQuery = useQuery({ queryKey: ["system-reports"], queryFn: api.reports });

  useEffect(() => {
    if (!settingsQuery.data) return;
    setEnabled(settingsQuery.data.report_enabled);
    setWeekday(String(settingsQuery.data.report_weekday));
    setHour(settingsQuery.data.report_hour);
    setKeep(settingsQuery.data.report_keep);
    setEmailTo(settingsQuery.data.report_email_to);
    setSmtpHost(settingsQuery.data.smtp_host);
    setSmtpPort(settingsQuery.data.smtp_port);
    setSmtpUser(settingsQuery.data.smtp_user);
    setSmtpFrom(settingsQuery.data.smtp_from);
    setSmtpTls(settingsQuery.data.smtp_tls);
    setSmtpSsl(settingsQuery.data.smtp_ssl);
  }, [settingsQuery.data]);

  const save = useMutation({
    mutationFn: () =>
      api.updateSystemSettings({
        report_enabled: enabled,
        report_weekday: Number(weekday),
        report_hour: hour,
        report_keep: keep,
        report_email_to: emailTo,
        smtp_host: smtpHost,
        smtp_port: smtpPort,
        smtp_user: smtpUser,
        smtp_from: smtpFrom,
        smtp_tls: smtpTls,
        smtp_ssl: smtpSsl,
        ...(smtpPassword ? { smtp_password: smtpPassword } : {}),
      }),
    onSuccess: () => {
      toast.success(t("reports.saved"));
      setSmtpPassword("");
      void queryClient.invalidateQueries({ queryKey: ["system-settings"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const run = useMutation({
    mutationFn: () => api.runReport(),
    onSuccess: () => {
      toast.success(t("reports.queued"));
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      window.setTimeout(() => void reportsQuery.refetch(), 2000);
    },
    onError: (error) => notifyError(t, error),
  });

  const testEmail = useMutation({
    mutationFn: () => api.testEmail(),
    onSuccess: (result) =>
      result.ok ? toast.success(t("reports.emailOk")) : toast.error(t("reports.emailFailed")),
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
            <Input type="number" min={0} max={23} value={hour} onChange={(event) => setHour(Number(event.target.value))} className="w-24" />
          </div>
          <div className="space-y-1">
            <Label>{t("reports.keep")}</Label>
            <Input type="number" min={1} max={200} value={keep} onChange={(event) => setKeep(Number(event.target.value))} className="w-24" />
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

        <div className="space-y-3 rounded-md border bg-muted/10 p-3">
          <p className="flex items-center gap-2 text-xs font-medium"><Mail className="h-3.5 w-3.5 text-primary" />{t("reports.emailTitle")}</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1"><Label>{t("reports.smtpHost")}</Label><Input value={smtpHost} onChange={(event) => setSmtpHost(event.target.value)} placeholder="smtp.example.com" /></div>
            <div className="space-y-1"><Label>{t("reports.smtpPort")}</Label><Input type="number" value={smtpPort} onChange={(event) => setSmtpPort(Number(event.target.value))} /></div>
            <div className="space-y-1"><Label>{t("reports.smtpUser")}</Label><Input value={smtpUser} onChange={(event) => setSmtpUser(event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("reports.smtpPassword")}</Label><Input type="password" autoComplete="new-password" value={smtpPassword} onChange={(event) => setSmtpPassword(event.target.value)} placeholder={settingsQuery.data?.has_smtp_password ? "••••••" : ""} /></div>
            <div className="space-y-1"><Label>{t("reports.smtpFrom")}</Label><Input value={smtpFrom} onChange={(event) => setSmtpFrom(event.target.value)} placeholder="oxidized@example.com" /></div>
            <div className="space-y-1"><Label>{t("reports.emailTo")}</Label><Input value={emailTo} onChange={(event) => setEmailTo(event.target.value)} placeholder="ops@example.com" /></div>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <label className="flex items-center gap-2"><Switch checked={smtpTls} onCheckedChange={setSmtpTls} />STARTTLS</label>
            <label className="flex items-center gap-2"><Switch checked={smtpSsl} onCheckedChange={setSmtpSsl} />SSL</label>
            <Button type="button" variant="outline" size="sm" disabled={testEmail.isPending} onClick={() => testEmail.mutate()}>
              {testEmail.isPending ? <Spinner /> : <Mail />}
              {t("reports.emailTest")}
            </Button>
          </div>
        </div>

        <p className="text-[11px] text-muted-foreground">{t("reports.help")}</p>

        <div className="space-y-1 border-t pt-3">
          <p className="text-[10px] uppercase tracking-[0.1em] text-muted-foreground">{t("reports.history")}</p>
          {(reportsQuery.data?.items ?? []).length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("reports.empty")}</p>
          ) : (
            (reportsQuery.data?.items ?? []).map((item) => (
              <div key={item.filename} className="flex items-center justify-between gap-2 py-1 text-xs">
                <span className="flex min-w-0 items-center gap-2">
                  <Badge variant="outline" className="uppercase">{item.format}</Badge>
                  <span className="min-w-0 truncate font-mono text-[10px]">{item.filename}</span>
                </span>
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
