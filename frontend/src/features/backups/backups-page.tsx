import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Check, Info, ListOrdered, Pencil, Plus, Trash2, TriangleAlert } from "lucide-react";
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
import { Switch } from "@/components/ui/switch";
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
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [ruleType, setRuleType] = useState<"group" | "tag">("group");
  const [ruleKey, setRuleKey] = useState("");
  const [ruleValue, setRuleValue] = useState("");
  const [rulePriority, setRulePriority] = useState(1);
  usePageTitle("nav.backups");

  const schedulesQuery = useQuery({
    queryKey: ["backup-schedules"],
    queryFn: api.backupSchedules,
    enabled: can("backups.trigger"),
  });
  const rulesQuery = useQuery({
    queryKey: ["priority-rules"],
    queryFn: api.priorityRules,
    enabled: can("backups.trigger"),
  });

  const createRule = useMutation({
    mutationFn: () =>
      api.createPriorityRule({
        scope_type: ruleType,
        scope_key: ruleKey.trim(),
        scope_value: ruleType === "tag" ? ruleValue.trim() : null,
        priority: rulePriority,
      }),
    onSuccess: () => {
      toast.success(t("backups.ruleCreated"));
      setRuleKey("");
      setRuleValue("");
      void queryClient.invalidateQueries({ queryKey: ["priority-rules"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const deleteRule = useMutation({
    mutationFn: (id: number) => api.deletePriorityRule(id),
    onSuccess: () => {
      toast.success(t("backups.ruleDeleted"));
      void queryClient.invalidateQueries({ queryKey: ["priority-rules"] });
    },
    onError: (error) => notifyError(t, error),
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

  const updateSchedule = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { interval_minutes?: number; enabled?: boolean } }) =>
      api.updateBackupSchedule(id, payload),
    onSuccess: () => {
      toast.success(t("backups.scheduleUpdated"));
      setEditingId(null);
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
              <div key={schedule.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-xs">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {schedule.group_name ?? t("logs.scheduleAllGroups")}
                    </span>
                    <span className="text-muted-foreground">
                      {t("backups.nodesCount", { count: schedule.node_count })}
                    </span>
                    {editingId === schedule.id ? (
                      <span className="inline-flex items-center gap-1">
                        <Input
                          type="number"
                          min={15}
                          max={10080}
                          value={editingValue}
                          onChange={(event) => setEditingValue(event.target.value)}
                          className="h-6 w-24 rounded px-1.5 py-0 text-[11px]"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          aria-label={t("common.save")}
                          disabled={updateSchedule.isPending || Number(editingValue) < 15}
                          onClick={() =>
                            updateSchedule.mutate({
                              id: schedule.id,
                              payload: { interval_minutes: Number(editingValue) },
                            })
                          }
                        >
                          {updateSchedule.isPending ? <Spinner /> : <Check />}
                        </Button>
                      </span>
                    ) : (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 font-mono text-[10px] hover:border-primary/40 hover:text-primary"
                        onClick={() => {
                          setEditingId(schedule.id);
                          setEditingValue(String(schedule.interval_minutes));
                        }}
                      >
                        {t("backups.everyCadence", { value: cadenceValue(schedule.interval_minutes) })}
                        <Pencil className="h-2.5 w-2.5" />
                      </button>
                    )}
                    {!schedule.enabled ? (
                      <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] text-muted-foreground">
                        {t("backups.paused")}
                      </span>
                    ) : null}
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {t("backups.lastRun", { value: schedule.last_run_at ? intl.dateTime(schedule.last_run_at) : t("backups.never") })}
                    {" · "}
                    {t("backups.nextRun", { value: schedule.next_run_at ? intl.dateTime(schedule.next_run_at) : "—" })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Switch
                    checked={schedule.enabled}
                    aria-label={t("backups.enabled")}
                    disabled={updateSchedule.isPending}
                    onCheckedChange={(checked) =>
                      updateSchedule.mutate({ id: schedule.id, payload: { enabled: checked } })
                    }
                  />
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
              </div>
            ))}
            {(schedules?.items ?? []).length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("logs.noSchedules")}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <ListOrdered className="h-4 w-4 text-primary" />
            {t("backups.priorityTitle")}
          </CardTitle>
          <CardDescription>{t("backups.priorityDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label>{t("backups.priorityScope")}</Label>
              <Select value={ruleType} onValueChange={(value) => setRuleType(value as "group" | "tag")}>
                <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="group">{t("backups.priorityGroup")}</SelectItem>
                  <SelectItem value="tag">{t("backups.priorityTag")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>{ruleType === "group" ? t("backups.priorityGroupName") : t("nodes.tagKey")}</Label>
              <Input value={ruleKey} maxLength={128} onChange={(event) => setRuleKey(event.target.value)} className="w-44" placeholder={ruleType === "group" ? "critical" : "tier"} />
            </div>
            {ruleType === "tag" ? (
              <div className="space-y-1">
                <Label>{t("nodes.tagValue")}</Label>
                <Input value={ruleValue} maxLength={128} onChange={(event) => setRuleValue(event.target.value)} className="w-36" placeholder="edge" />
              </div>
            ) : null}
            <div className="space-y-1">
              <Label>{t("backups.priorityLevel")}</Label>
              <Input
                type="number"
                min={1}
                max={10}
                value={rulePriority}
                onChange={(event) => setRulePriority(Number(event.target.value))}
                className="w-24"
              />
            </div>
            <Button
              type="button"
              size="sm"
              disabled={createRule.isPending || !ruleKey.trim() || (ruleType === "tag" && !ruleValue.trim())}
              onClick={() => createRule.mutate()}
            >
              {createRule.isPending ? <Spinner /> : <Plus />}
              {t("backups.priorityAdd")}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">{t("backups.priorityHelp")}</p>
          <div className="divide-y">
            {(rulesQuery.data?.items ?? []).map((rule) => (
              <div key={rule.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                <span className="font-mono">
                  {rule.scope_type === "group"
                    ? `${t("backups.priorityGroup")}: ${rule.scope_key}`
                    : `${t("backups.priorityTag")}: ${rule.scope_key}=${rule.scope_value}`}
                  <span className="ml-2 rounded-full border border-border/70 bg-muted/40 px-2 py-0.5 text-[10px]">
                    {t("backups.priorityValue", { value: rule.priority })}
                  </span>
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => deleteRule.mutate(rule.id)}
                >
                  <Trash2 />
                  {t("common.delete")}
                </Button>
              </div>
            ))}
            {(rulesQuery.data?.items ?? []).length === 0 ? (
              <p className="py-2 text-xs text-muted-foreground">{t("backups.priorityEmpty")}</p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
