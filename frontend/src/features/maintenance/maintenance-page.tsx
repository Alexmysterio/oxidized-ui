import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarOff, ShieldCheck, Trash2, Wrench } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";

function toLocalInput(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function MaintenancePage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [scopeType, setScopeType] = useState<"group" | "node" | "global">("group");
  const [group, setGroup] = useState("");
  const [nodeId, setNodeId] = useState("");
  const [startsAt, setStartsAt] = useState(() => toLocalInput(new Date()));
  const [endsAt, setEndsAt] = useState(() => toLocalInput(new Date(Date.now() + 60 * 60_000)));
  const [reason, setReason] = useState("");
  usePageTitle("nav.maintenance");

  const windowsQuery = useQuery({ queryKey: ["maintenance"], queryFn: () => api.maintenanceWindows() });
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: api.groups,
    enabled: can("groups.write"),
  });
  const nodesQuery = useQuery({
    queryKey: ["nodes", "maintenance-picker"],
    queryFn: () => api.nodes({ page: 1, page_size: 100, sort: "name" }),
    enabled: scopeType === "node",
  });

  const create = useMutation({
    mutationFn: () =>
      api.createMaintenanceWindow({
        scope_type: scopeType,
        group_name: scopeType === "group" ? group : null,
        node_id: scopeType === "node" ? Number(nodeId) : null,
        starts_at: new Date(startsAt).toISOString(),
        ends_at: new Date(endsAt).toISOString(),
        reason: reason.trim() || null,
      }),
    onSuccess: () => {
      toast.success(t("maintenance.created"));
      setReason("");
      void queryClient.invalidateQueries({ queryKey: ["maintenance"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteMaintenanceWindow(id),
    onSuccess: () => {
      toast.success(t("maintenance.deleted"));
      void queryClient.invalidateQueries({ queryKey: ["maintenance"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const groups = (groupsQuery.data?.groups ?? []).filter((item) => item.state === "applied");
  const nodes = nodesQuery.data?.items ?? [];
  const canSubmit =
    scopeType === "global" || (scopeType === "group" && group) || (scopeType === "node" && nodeId);

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><Wrench className="h-3.5 w-3.5 text-primary" />{t("nav.operations")}</>}
        title={t("nav.maintenance")}
        description={t("maintenance.subtitle")}
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <CalendarOff className="h-4 w-4 text-primary" />
            {t("maintenance.newWindow")}
          </CardTitle>
          <CardDescription>{t("maintenance.newWindowDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label>{t("maintenance.scope")}</Label>
              <Select value={scopeType} onValueChange={(value) => setScopeType(value as typeof scopeType)}>
                <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="group">{t("maintenance.scopeGroup")}</SelectItem>
                  <SelectItem value="node">{t("maintenance.scopeNode")}</SelectItem>
                  <SelectItem value="global">{t("maintenance.scopeGlobal")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {scopeType === "group" ? (
              <div className="space-y-1">
                <Label>{t("maintenance.group")}</Label>
                <Select value={group} onValueChange={setGroup}>
                  <SelectTrigger className="w-48"><SelectValue placeholder={t("maintenance.selectGroup")} /></SelectTrigger>
                  <SelectContent>
                    {groups.map((item) => (
                      <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            {scopeType === "node" ? (
              <div className="space-y-1">
                <Label>{t("maintenance.node")}</Label>
                <Select value={nodeId} onValueChange={setNodeId}>
                  <SelectTrigger className="w-56"><SelectValue placeholder={t("maintenance.selectNode")} /></SelectTrigger>
                  <SelectContent>
                    {nodes.map((node) => (
                      <SelectItem key={node.id} value={String(node.id)}>{node.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}
            <div className="space-y-1">
              <Label>{t("maintenance.from")}</Label>
              <Input type="datetime-local" value={startsAt} onChange={(event) => setStartsAt(event.target.value)} className="w-52" />
            </div>
            <div className="space-y-1">
              <Label>{t("maintenance.to")}</Label>
              <Input type="datetime-local" value={endsAt} onChange={(event) => setEndsAt(event.target.value)} className="w-52" />
            </div>
            <div className="min-w-[12rem] flex-1 space-y-1">
              <Label>{t("maintenance.reason")}</Label>
              <Input value={reason} maxLength={255} onChange={(event) => setReason(event.target.value)} placeholder={t("maintenance.reasonPlaceholder")} />
            </div>
            <Button type="button" size="sm" disabled={!canSubmit || create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? <Spinner /> : <Wrench />}
              {t("maintenance.create")}
            </Button>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">{t("maintenance.hint")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("maintenance.activeWindows")}</CardTitle>
          <CardDescription>{t("maintenance.activeWindowsDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {windowsQuery.isLoading ? (
            <div className="h-16 animate-pulse rounded-md bg-muted" />
          ) : windowsQuery.isError ? (
            <ErrorState onRetry={() => void windowsQuery.refetch()} compact />
          ) : !(windowsQuery.data?.items ?? []).length ? (
            <EmptyState icon={ShieldCheck} title={t("maintenance.emptyTitle")} description={t("maintenance.emptyDescription")} compact />
          ) : (
            (windowsQuery.data?.items ?? []).map((window) => (
              <div key={window.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs">
                <div className="min-w-0 space-y-0.5">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">
                      {window.scope_type === "global"
                        ? t("maintenance.scopeGlobal")
                        : window.scope_type === "group"
                          ? window.group_name
                          : window.node_name ?? `#${window.node_id}`}
                    </span>
                    <Badge variant={window.active ? "warning" : "outline"}>
                      {window.active ? t("maintenance.active") : t("maintenance.scheduled")}
                    </Badge>
                    {window.reason ? <span className="text-muted-foreground">{window.reason}</span> : null}
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {intl.dateTime(window.starts_at)} → {intl.dateTime(window.ends_at)}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => remove.mutate(window.id)}
                >
                  <Trash2 />
                  {t("common.delete")}
                </Button>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
