import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Bot, Globe, MessageCircle, Pencil, Plus, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import type { TFunction } from "i18next";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import type { NotificationChannel, NotificationEvent, NotificationKind } from "@/types/api";

const KINDS: NotificationKind[] = ["webhook", "slack", "discord", "telegram"];
const EVENTS: NotificationEvent[] = ["job.failed", "backup.stale"];

const KIND_ICONS = {
  webhook: Globe,
  slack: MessageCircle,
  discord: Bot,
  telegram: Send,
} as const;

function kindLabel(t: TFunction, kind: NotificationKind): string {
  return {
    webhook: t("system.kindWebhook"),
    slack: t("system.kindSlack"),
    discord: t("system.kindDiscord"),
    telegram: t("system.kindTelegram"),
  }[kind];
}

function eventLabel(t: TFunction, event: NotificationEvent): string {
  return {
    "job.failed": t("system.eventJobFailed"),
    "backup.stale": t("system.eventBackupStale"),
  }[event];
}

export function NotificationsCard() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<NotificationChannel | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<NotificationKind>("webhook");
  const [enabled, setEnabled] = useState(true);
  const [events, setEvents] = useState<NotificationEvent[]>(["job.failed", "backup.stale"]);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const channelsQuery = useQuery({ queryKey: ["notification-channels"], queryFn: api.notifications });

  const reset = (channel: NotificationChannel | null) => {
    setEditing(channel);
    setName(channel?.name ?? "");
    setKind(channel?.kind ?? "webhook");
    setEnabled(channel?.enabled ?? true);
    setEvents(channel?.events?.length ? channel.events : ["job.failed", "backup.stale"]);
    setConfig(channel?.config ?? {});
    setError(null);
  };

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        name: name.trim(),
        kind,
        enabled,
        events,
        config: Object.fromEntries(Object.entries(config).filter(([, value]) => value.trim())),
      };
      return editing
        ? api.updateNotification(editing.id, payload)
        : api.createNotification(payload);
    },
    onSuccess: () => {
      toast.success(editing ? t("system.channelUpdated") : t("system.channelCreated"));
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["notification-channels"] });
    },
    onError: (caught) => setError(errorMessage(t, caught)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteNotification(id),
    onSuccess: () => {
      toast.success(t("system.channelDeleted"));
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["notification-channels"] });
    },
    onError: (caught) => toast.error(t("errors.title"), { description: errorMessage(t, caught) }),
  });

  const test = useMutation({
    mutationFn: (id: number) => api.testNotificationChannel(id),
    onSuccess: (result) => {
      if (result.ok) toast.success(t("system.testOk"));
      else toast.error(t("system.testFailed"));
    },
    onError: (caught) => toast.error(t("errors.title"), { description: errorMessage(t, caught) }),
  });

  const channels = channelsQuery.data?.items ?? [];

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-4 w-4 text-primary" />
                {t("system.notificationChannels")}
              </CardTitle>
              <CardDescription>{t("system.notificationChannelsDescription")}</CardDescription>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => { reset(null); setOpen(true); }}>
              <Plus />
              {t("system.addChannel")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {channelsQuery.isLoading ? (
            <div className="h-12 animate-pulse rounded-md bg-muted" />
          ) : channels.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-xs text-muted-foreground">{t("system.noChannels")}</p>
          ) : (
            channels.map((channel) => {
              const Icon = KIND_ICONS[channel.kind] ?? Globe;
              return (
                <div key={channel.id} className="flex flex-wrap items-center gap-3 rounded-lg border bg-muted/10 px-3 py-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="truncate text-xs font-medium">{channel.name}</span>
                      <Badge variant={channel.enabled ? "success" : "outline"} className="text-[9px]">
                        {channel.enabled ? t("system.channelEnabled") : t("system.channelDisabled")}
                      </Badge>
                      <span className="text-[10px] text-muted-foreground">{kindLabel(t, channel.kind)}</span>
                    </div>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      {channel.events.map((event) => eventLabel(t, event)).join(" · ")}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button type="button" variant="ghost" size="icon-xs" onClick={() => test.mutate(channel.id)} disabled={test.isPending} title={t("system.testChannel")}>
                      {test.isPending ? <Spinner /> : <Send />}
                    </Button>
                    <Button type="button" variant="ghost" size="icon-xs" onClick={() => { reset(channel); setOpen(true); }} title={t("common.edit")}>
                      <Pencil />
                    </Button>
                    <Button type="button" variant="ghost" size="icon-xs" className="text-muted-foreground hover:text-destructive" onClick={() => setDeleteTarget(channel)} title={t("common.delete")}>
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? t("system.editChannel") : t("system.addChannel")}</DialogTitle>
            <DialogDescription>{t("system.channelDialogDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {error ? <p className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">{error}</p> : null}
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="channel-name">{t("system.channelName")}</Label>
                <Input id="channel-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Ops alerts" />
              </div>
              <div className="space-y-2">
                <Label>{t("system.channelKind")}</Label>
                <Select value={kind} onValueChange={(value) => { setKind(value as NotificationKind); setConfig({}); }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {KINDS.map((value) => (
                      <SelectItem key={value} value={value}>{kindLabel(t, value)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center justify-between rounded-md border p-3">
              <span className="text-xs font-medium">{t("system.channelEnabled")}</span>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </div>

            <div className="space-y-2">
              <Label>{t("system.channelEvents")}</Label>
              <div className="flex flex-wrap gap-4">
                {EVENTS.map((event) => (
                  <label key={event} className="flex items-center gap-2 text-xs">
                    <Checkbox
                      checked={events.includes(event)}
                      onCheckedChange={(value) =>
                        setEvents((current) =>
                          value === true ? [...current, event] : current.filter((item) => item !== event),
                        )
                      }
                    />
                    {eventLabel(t, event)}
                  </label>
                ))}
              </div>
            </div>

            {kind === "telegram" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="channel-telegram-token">{t("system.telegramBotToken")}</Label>
                  <Input id="channel-telegram-token" value={config.bot_token ?? ""} onChange={(event) => setConfig((current) => ({ ...current, bot_token: event.target.value }))} placeholder="123456:ABC..." />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="channel-telegram-chat">{t("system.telegramChatId")}</Label>
                  <Input id="channel-telegram-chat" value={config.chat_id ?? ""} onChange={(event) => setConfig((current) => ({ ...current, chat_id: event.target.value }))} placeholder="-1001234567890" />
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Label htmlFor="channel-url">
                  {kind === "webhook" ? t("system.webhookUrl") : kind === "slack" ? t("system.slackWebhook") : t("system.discordWebhook")}
                </Label>
                <Input
                  id="channel-url"
                  type="url"
                  value={config[kind === "webhook" ? "url" : "webhook_url"] ?? ""}
                  onChange={(event) =>
                    setConfig((current) => ({ ...current, [kind === "webhook" ? "url" : "webhook_url"]: event.target.value }))
                  }
                  placeholder="https://..."
                />
                <p className="text-[11px] text-muted-foreground">{t("system.channelUrlHelp")}</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>{t("common.cancel")}</Button>
            <Button type="button" onClick={() => save.mutate()} disabled={save.isPending || !name.trim() || events.length === 0}>
              {save.isPending ? <Spinner /> : null}
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(value) => { if (!value) setDeleteTarget(null); }}
        title={t("system.deleteChannelTitle")}
        description={t("system.deleteChannelDescription", { name: deleteTarget?.name ?? "" })}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
      />
    </>
  );
}
