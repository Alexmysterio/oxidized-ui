import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CloudUpload, HardDriveDownload, Play } from "lucide-react";
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
import { api } from "@/lib/api";
import { notifyError } from "@/lib/errors";

type Kind = "sftp" | "s3";

export function ExportCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<Kind>("sftp");
  const [intervalHours, setIntervalHours] = useState(24);
  const [enabled, setEnabled] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({
    host: "",
    port: "22",
    username: "",
    password: "",
    remote_dir: "/backups",
    endpoint_url: "",
    region: "us-east-1",
    bucket: "",
    prefix: "oxidized-ui",
    access_key: "",
    secret_key: "",
  });

  const statusQuery = useQuery({ queryKey: ["export-status"], queryFn: api.exportStatus });
  const status = statusQuery.data;

  useEffect(() => {
    if (!status) return;
    setEnabled(status.enabled);
    setIntervalHours(status.interval_hours);
    if (status.target.kind) {
      setKind(status.target.kind);
      setFields((current) => ({
        ...current,
        host: status.target.host ?? current.host,
        port: String(status.target.port ?? current.port),
        username: status.target.username ?? current.username,
        remote_dir: status.target.remote_dir ?? current.remote_dir,
        endpoint_url: status.target.endpoint_url ?? current.endpoint_url,
        region: status.target.region ?? current.region,
        bucket: status.target.bucket ?? current.bucket,
        prefix: status.target.prefix ?? current.prefix,
      }));
    }
  }, [status]);

  const configure = useMutation({
    mutationFn: () => {
      const base = { passphrase };
      const config =
        kind === "sftp"
          ? {
              ...base,
              host: fields.host,
              port: Number(fields.port || 22),
              username: fields.username,
              password: fields.password,
              remote_dir: fields.remote_dir,
            }
          : {
              ...base,
              endpoint_url: fields.endpoint_url,
              region: fields.region,
              bucket: fields.bucket,
              prefix: fields.prefix,
              access_key: fields.access_key,
              secret_key: fields.secret_key,
            };
      return api.configureExport({ kind, interval_hours: intervalHours, enabled, config });
    },
    onSuccess: () => {
      toast.success(t("system.exportSaved"));
      setPassphrase("");
      void queryClient.invalidateQueries({ queryKey: ["export-status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const runNow = useMutation({
    mutationFn: () => api.runExport(),
    onSuccess: () => {
      toast.success(t("system.exportQueued"));
      void queryClient.invalidateQueries({ queryKey: ["export-status"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const update = (key: string, value: string) => setFields((current) => ({ ...current, [key]: value }));
  const canSave = Boolean(passphrase.length >= 12) && (kind === "s3" ? Boolean(fields.bucket) : Boolean(fields.host && fields.username));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CloudUpload className="h-4 w-4 text-primary" />
          {t("system.exportTitle")}
        </CardTitle>
        <CardDescription>{t("system.exportDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label>{t("system.exportKind")}</Label>
            <Select value={kind} onValueChange={(value) => setKind(value as Kind)}>
              <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="sftp">SFTP</SelectItem>
                <SelectItem value="s3">S3</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>{t("system.exportInterval")}</Label>
            <Input
              type="number"
              min={1}
              max={720}
              value={intervalHours}
              onChange={(event) => setIntervalHours(Number(event.target.value))}
              className="w-28"
            />
          </div>
          <label className="flex items-center gap-2 pb-2 text-xs">
            <Switch checked={enabled} onCheckedChange={setEnabled} />
            {t("system.exportEnabled")}
          </label>
        </div>

        {kind === "sftp" ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1"><Label>{t("system.exportHost")}</Label><Input value={fields.host} onChange={(event) => update("host", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportPort")}</Label><Input value={fields.port} onChange={(event) => update("port", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportUsername")}</Label><Input value={fields.username} onChange={(event) => update("username", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportPassword")}</Label><Input type="password" autoComplete="new-password" value={fields.password} onChange={(event) => update("password", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportRemoteDir")}</Label><Input value={fields.remote_dir} onChange={(event) => update("remote_dir", event.target.value)} /></div>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1"><Label>{t("system.exportEndpoint")}</Label><Input value={fields.endpoint_url} onChange={(event) => update("endpoint_url", event.target.value)} placeholder="https://s3.example.com" /></div>
            <div className="space-y-1"><Label>{t("system.exportRegion")}</Label><Input value={fields.region} onChange={(event) => update("region", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportBucket")}</Label><Input value={fields.bucket} onChange={(event) => update("bucket", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportPrefix")}</Label><Input value={fields.prefix} onChange={(event) => update("prefix", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportAccessKey")}</Label><Input value={fields.access_key} onChange={(event) => update("access_key", event.target.value)} /></div>
            <div className="space-y-1"><Label>{t("system.exportSecretKey")}</Label><Input type="password" autoComplete="new-password" value={fields.secret_key} onChange={(event) => update("secret_key", event.target.value)} /></div>
          </div>
        )}

        <div className="space-y-1">
          <Label>{t("system.exportPassphrase")}</Label>
          <Input
            type="password"
            autoComplete="new-password"
            value={passphrase}
            onChange={(event) => setPassphrase(event.target.value)}
            placeholder={t("system.exportPassphrasePlaceholder")}
          />
          <p className="text-[10px] text-muted-foreground">{t("system.exportPassphraseHelp")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" disabled={!canSave || configure.isPending} onClick={() => configure.mutate()}>
            {configure.isPending ? <Spinner /> : <HardDriveDownload />}
            {t("system.exportSave")}
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={runNow.isPending} onClick={() => runNow.mutate()}>
            {runNow.isPending ? <Spinner /> : <Play />}
            {t("system.exportRunNow")}
          </Button>
          {status?.configured ? (
            <Badge variant={status.last_status === "failed" ? "destructive" : status.enabled ? "success" : "outline"}>
              {status.last_status ?? t("system.exportNeverRun")}
            </Badge>
          ) : (
            <Badge variant="outline">{t("system.exportNotConfigured")}</Badge>
          )}
        </div>

        {status?.last_error ? <p className="text-[11px] text-destructive">{status.last_error}</p> : null}
        {status?.next_run_at ? (
          <p className="font-mono text-[10px] text-muted-foreground">
            {t("system.exportNextRun", { value: status.next_run_at })}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
