import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock3, Download, PlugZap, Save, ServerCog, Settings2, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { PageSkeleton, Spinner } from "@/components/shared/loaders";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { SystemSettings } from "@/types/api";

interface FormValues {
  oxidized_api_url: string;
  oxidized_container_name: string;
  docker_proxy_url: string;
  timezone: string;
  activity_retention_days: number;
  audit_retention_days: number;
  poll_interval_seconds: number;
  log_tail_default: number;
  config_backup_keep: number;
  password_min_length: number;
  password_require_complexity: boolean;
  password_history_count: number;
  login_max_failures_per_user: number;
  login_max_failures_per_ip: number;
  login_window_minutes: number;
  login_lockout_minutes: number;
  ip_allowlist: string;
  notify_webhook_url: string;
  notify_on_failure: boolean;
  notify_stale_hours: number;
}

function valuesFrom(settings: SystemSettings): FormValues {
  return {
    oxidized_api_url: settings.oxidized_api_url,
    oxidized_container_name: settings.oxidized_container_name,
    docker_proxy_url: settings.docker_proxy_url,
    timezone: settings.timezone ?? "",
    activity_retention_days: settings.activity_retention_days,
    audit_retention_days: settings.audit_retention_days,
    poll_interval_seconds: settings.poll_interval_seconds,
    log_tail_default: settings.log_tail_default,
    config_backup_keep: settings.config_backup_keep,
    password_min_length: settings.password_min_length,
    password_require_complexity: settings.password_require_complexity,
    password_history_count: settings.password_history_count,
    login_max_failures_per_user: settings.login_max_failures_per_user,
    login_max_failures_per_ip: settings.login_max_failures_per_ip,
    login_window_minutes: settings.login_window_minutes,
    login_lockout_minutes: settings.login_lockout_minutes,
    ip_allowlist: settings.ip_allowlist,
    notify_webhook_url: settings.notify_webhook_url,
    notify_on_failure: settings.notify_on_failure,
    notify_stale_hours: settings.notify_stale_hours,
  };
}

export function SystemPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, boolean>>({});
  const [testing, setTesting] = useState<string | null>(null);
  usePageTitle("nav.system");

  const schema = z.object({
    oxidized_api_url: z.string().url(t("validation.url")),
    oxidized_container_name: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/, t("validation.containerName")),
    docker_proxy_url: z.string().url(t("validation.url")),
    timezone: z.string(),
    activity_retention_days: z.coerce
      .number({ invalid_type_error: t("validation.number") })
      .int(t("validation.number"))
      .min(0, t("validation.range", { min: 0, max: 3650 }))
      .max(3650, t("validation.range", { min: 0, max: 3650 })),
    audit_retention_days: z.coerce.number().int().min(7).max(3650),
    poll_interval_seconds: z.coerce
      .number({ invalid_type_error: t("validation.number") })
      .int(t("validation.number"))
      .min(5, t("validation.range", { min: 5, max: 3600 }))
      .max(3600, t("validation.range", { min: 5, max: 3600 })),
    log_tail_default: z.coerce
      .number({ invalid_type_error: t("validation.number") })
      .int(t("validation.number"))
      .min(50, t("validation.range", { min: 50, max: 5000 }))
      .max(5000, t("validation.range", { min: 50, max: 5000 })),
    config_backup_keep: z.coerce
      .number({ invalid_type_error: t("validation.number") })
      .int(t("validation.number"))
      .min(0, t("validation.range", { min: 0, max: 100 }))
      .max(100, t("validation.range", { min: 0, max: 100 })),
    password_min_length: z.coerce.number().int().min(8).max(128),
    password_require_complexity: z.boolean(),
    password_history_count: z.coerce.number().int().min(0).max(24),
    login_max_failures_per_user: z.coerce.number().int().min(1).max(100),
    login_max_failures_per_ip: z.coerce.number().int().min(1).max(1000),
    login_window_minutes: z.coerce.number().int().min(1).max(1440),
    login_lockout_minutes: z.coerce.number().int().min(1).max(1440),
    ip_allowlist: z.string().max(8192),
    notify_webhook_url: z.string().max(2048),
    notify_on_failure: z.boolean(),
    notify_stale_hours: z.coerce.number().int().min(0).max(720),
  });

  const settingsQuery = useQuery({ queryKey: ["system-settings"], queryFn: api.systemSettings });
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      oxidized_api_url: "",
      oxidized_container_name: "",
      docker_proxy_url: "",
      timezone: "",
      activity_retention_days: 0,
      audit_retention_days: 180,
      poll_interval_seconds: 60,
      log_tail_default: 500,
      config_backup_keep: 0,
      password_min_length: 12,
      password_require_complexity: true,
      password_history_count: 5,
      login_max_failures_per_user: 5,
      login_max_failures_per_ip: 20,
      login_window_minutes: 15,
      login_lockout_minutes: 30,
      ip_allowlist: "",
      notify_webhook_url: "",
      notify_on_failure: true,
      notify_stale_hours: 0,
    },
  });

  useEffect(() => {
    if (settingsQuery.data) form.reset(valuesFrom(settingsQuery.data));
  }, [settingsQuery.data, form]);

  const save = useMutation({
    mutationFn: (values: FormValues) => api.updateSystemSettings({ ...values, timezone: values.timezone || null }),
    onSuccess: async () => {
      toast.success(t("system.saved"));
      setServerError(null);
      await queryClient.invalidateQueries({ queryKey: ["system-settings"] });
      await queryClient.invalidateQueries({ queryKey: ["meta"] });
      await queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => setServerError(errorMessage(t, error)),
  });

  const test = async (target: "oxidized" | "docker") => {
    setTesting(target);
    try {
      const result = await api.testConnection(target);
      setTestResults((current) => ({ ...current, [target]: result.ok }));
      if (result.ok) toast.success(t("system.testSuccess"));
    } catch (error) {
      setTestResults((current) => ({ ...current, [target]: false }));
      toast.error(t("errors.title"), { description: errorMessage(t, error) });
    } finally {
      setTesting(null);
    }
  };

  const submit = form.handleSubmit((values) => save.mutate(values as FormValues));

  if (settingsQuery.isLoading) return <PageSkeleton />;
  if (settingsQuery.isError || !settingsQuery.data) return <ErrorState onRetry={() => void settingsQuery.refetch()} />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><ShieldCheck className="h-3.5 w-3.5 text-primary" />{t("nav.administration")}</>}
        title={t("system.title")}
        description={t("system.subtitle")}
        actions={
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              const passphrase = window.prompt(t("system.exportPassphrase"));
              if (passphrase) {
                void api.exportEncrypted(passphrase).catch((error: unknown) => {
                  toast.error(t("errors.title"), { description: errorMessage(t, error) });
                });
              }
            }}
          >
            <Download />
            {t("system.exportEncrypted")}
          </Button>
        }
      />

      <form onSubmit={submit} className="space-y-4" noValidate>
        {serverError ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5" />
            {serverError}
          </div>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><PlugZap className="h-4 w-4 text-primary" />{t("system.connection")}</CardTitle>
            <CardDescription>{t("system.connectionDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="oxidized-api">{t("system.oxidizedApiUrl")}</Label>
                <div className="flex gap-2">
                  <Input id="oxidized-api" className="font-mono text-xs" {...form.register("oxidized_api_url")} />
                  <Button type="button" variant="outline" size="sm" onClick={() => void test("oxidized")} disabled={testing === "oxidized"}>
                    {testing === "oxidized" ? <Spinner /> : testResults.oxidized === true ? <CheckCircle2 className="text-success" /> : testResults.oxidized === false ? <XCircle className="text-destructive" /> : <PlugZap />}
                    {t("system.testOxidized")}
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">{t("system.oxidizedApiUrlHelp")}</p>
                {form.formState.errors.oxidized_api_url ? <p className="text-xs text-destructive">{form.formState.errors.oxidized_api_url.message}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="docker-proxy">{t("system.dockerProxyUrl")}</Label>
                <div className="flex gap-2">
                  <Input id="docker-proxy" className="font-mono text-xs" {...form.register("docker_proxy_url")} />
                  <Button type="button" variant="outline" size="sm" onClick={() => void test("docker")} disabled={testing === "docker"}>
                    {testing === "docker" ? <Spinner /> : testResults.docker === true ? <CheckCircle2 className="text-success" /> : testResults.docker === false ? <XCircle className="text-destructive" /> : <PlugZap />}
                    {t("system.testDocker")}
                  </Button>
                </div>
                <p className="text-[11px] text-muted-foreground">{t("system.dockerProxyUrlHelp")}</p>
                {form.formState.errors.docker_proxy_url ? <p className="text-xs text-destructive">{form.formState.errors.docker_proxy_url.message}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="container-name">{t("system.containerName")}</Label>
                <Input id="container-name" className="font-mono text-xs" {...form.register("oxidized_container_name")} />
                <p className="text-[11px] text-muted-foreground">{t("system.containerNameHelp")}</p>
                {form.formState.errors.oxidized_container_name ? <p className="text-xs text-destructive">{form.formState.errors.oxidized_container_name.message}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="timezone">{t("system.timezone")}</Label>
                <Input id="timezone" list="timezone-options" className="font-mono text-xs" placeholder="Europe/Madrid" {...form.register("timezone")} />
                <datalist id="timezone-options">
                  {["UTC", "Europe/Madrid", "Europe/London", "America/New_York", "America/Bogota", "America/Mexico_City", "America/Sao_Paulo", "Asia/Tokyo", "Australia/Sydney"].map((zone) => <option key={zone} value={zone} />)}
                </datalist>
                <p className="text-[11px] text-muted-foreground">{t("system.timezoneHelp")}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Settings2 className="h-4 w-4 text-primary" />{t("system.behavior")}</CardTitle>
            <CardDescription>{t("system.behaviorDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2">
                <Label htmlFor="poll-interval">{t("system.pollInterval")}</Label>
                <Input id="poll-interval" type="number" min={5} max={3600} {...form.register("poll_interval_seconds", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="activity-retention">{t("system.activityRetention")}</Label>
                <Input id="activity-retention" type="number" min={0} max={3650} {...form.register("activity_retention_days", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="audit-retention">{t("system.auditRetention")}</Label>
                <Input id="audit-retention" type="number" min={7} max={3650} {...form.register("audit_retention_days", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="log-tail">{t("system.logTail")}</Label>
                <Input id="log-tail" type="number" min={50} max={5000} {...form.register("log_tail_default", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="backup-keep">{t("system.backupKeep")}</Label>
                <Input id="backup-keep" type="number" min={0} max={500} {...form.register("config_backup_keep", { valueAsNumber: true })} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />{t("system.securityPolicy")}</CardTitle>
            <CardDescription>{t("system.securityPolicyDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2">
                <Label htmlFor="password-min-length">{t("system.passwordMinLength")}</Label>
                <Input id="password-min-length" type="number" min={8} max={128} {...form.register("password_min_length", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password-history">{t("system.passwordHistoryCount")}</Label>
                <Input id="password-history" type="number" min={0} max={24} {...form.register("password_history_count", { valueAsNumber: true })} />
              </div>
              <div className="flex items-center justify-between gap-3 rounded-md border p-3 sm:col-span-2">
                <div>
                  <Label htmlFor="password-complexity">{t("system.passwordRequireComplexity")}</Label>
                  <p className="mt-1 text-[11px] text-muted-foreground">{t("system.passwordRequireComplexityHelp")}</p>
                </div>
                <Switch
                  id="password-complexity"
                  checked={form.watch("password_require_complexity")}
                  onCheckedChange={(value) => form.setValue("password_require_complexity", value, { shouldDirty: true })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-user-failures">{t("system.loginMaxFailuresUser")}</Label>
                <Input id="login-user-failures" type="number" min={1} max={100} {...form.register("login_max_failures_per_user", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-ip-failures">{t("system.loginMaxFailuresIp")}</Label>
                <Input id="login-ip-failures" type="number" min={1} max={1000} {...form.register("login_max_failures_per_ip", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-window">{t("system.loginWindow")}</Label>
                <Input id="login-window" type="number" min={1} max={1440} {...form.register("login_window_minutes", { valueAsNumber: true })} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="login-lockout">{t("system.loginLockout")}</Label>
                <Input id="login-lockout" type="number" min={1} max={1440} {...form.register("login_lockout_minutes", { valueAsNumber: true })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ip-allowlist">{t("system.ipAllowlist")}</Label>
              <Textarea id="ip-allowlist" rows={4} className="font-mono text-xs" placeholder="192.168.2.0/24" {...form.register("ip_allowlist")} />
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("system.ipAllowlistHelp")}</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />{t("system.notifications")}</CardTitle>
            <CardDescription>{t("system.notificationsDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="notify-webhook">{t("system.webhookUrl")}</Label>
              <Input id="notify-webhook" type="url" placeholder="https://hooks.slack.com/..." {...form.register("notify_webhook_url")} />
              <p className="text-[11px] text-muted-foreground">{t("system.webhookHelp")}</p>
            </div>
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-xs"><Switch checked={form.watch("notify_on_failure")} onCheckedChange={(value) => form.setValue("notify_on_failure", value, { shouldDirty: true })} />{t("system.notifyOnFailure")}</label>
              <label className="flex items-center gap-2 text-xs">{t("system.notifyStaleHours")}<Input type="number" min={0} max={720} className="w-24" {...form.register("notify_stale_hours", { valueAsNumber: true })} /></label>
              <Button type="button" variant="outline" size="sm" onClick={() => void api.testNotification().then((r) => toast.success(r.ok ? t("system.notificationSent") : t("system.notificationNotConfigured"))).catch((error) => toast.error(t("errors.title"), { description: errorMessage(t, error) }))}>{t("system.testNotification")}</Button>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button type="submit" size="sm" disabled={save.isPending || !form.formState.isDirty}>
            {save.isPending ? <Spinner /> : <Save />}
            {t("system.save")}
          </Button>
        </div>
      </form>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ServerCog className="h-4 w-4 text-primary" />{t("system.environmentValues")}</CardTitle>
          <CardDescription>{t("system.environmentNote")}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-3">
            {Object.entries(settingsQuery.data.environment).map(([key, value]) => (
              <div key={key} className="bg-card p-3">
                <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-muted-foreground">{key}</p>
                <p className="mt-1 break-all font-mono text-[11px]">{value}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground">
            <Clock3 className="h-3.5 w-3.5" />
            {t("system.timezone")}: {settingsQuery.data.timezone ?? t("system.browserTimezone")}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
