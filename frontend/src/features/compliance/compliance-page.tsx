import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileWarning, Plus, Scale, Trash2, TriangleAlert, XCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { DiffView } from "@/components/shared/diff-view";
import { EmptyState } from "@/components/shared/empty-state";
import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import type { ComplianceStatus, ConfigTemplate } from "@/types/api";

const statusVariants: Record<ComplianceStatus, "success" | "destructive" | "warning" | "outline"> = {
  compliant: "success",
  deviating: "destructive",
  no_template: "outline",
  error: "warning",
};

const emptyForm = { name: "", scope_type: "global" as ConfigTemplate["scope_type"], scope_value: "", content: "" };

export function CompliancePage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [group, setGroup] = useState("__all__");
  const [templateFilter, setTemplateFilter] = useState("__auto__");
  const [openNode, setOpenNode] = useState<number | null>(null);
  usePageTitle("nav.compliance");

  const templatesQuery = useQuery({ queryKey: ["compliance-templates"], queryFn: api.complianceTemplates });
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: api.groups,
    enabled: can("groups.write"),
  });
  const reportQuery = useQuery({
    queryKey: ["compliance-report", group, templateFilter],
    queryFn: () =>
      api.complianceReport({
        group: group === "__all__" ? undefined : group,
        template_id: templateFilter === "__auto__" ? undefined : Number(templateFilter),
      }),
  });
  const nodeReportQuery = useQuery({
    queryKey: ["compliance-node", openNode],
    queryFn: () => api.complianceNodeReport(openNode as number),
    enabled: openNode !== null,
  });

  const save = useMutation({
    mutationFn: () =>
      editingId
        ? api.updateComplianceTemplate(editingId, {
            name: form.name,
            scope_type: form.scope_type,
            scope_value: form.scope_type === "global" ? null : form.scope_value,
            content: form.content,
          })
        : api.createComplianceTemplate({
            name: form.name,
            scope_type: form.scope_type,
            scope_value: form.scope_type === "global" ? null : form.scope_value,
            content: form.content,
          }),
    onSuccess: () => {
      toast.success(t("compliance.saved"));
      setForm(emptyForm);
      setEditingId(null);
      void queryClient.invalidateQueries({ queryKey: ["compliance-templates"] });
      void queryClient.invalidateQueries({ queryKey: ["compliance-report"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteComplianceTemplate(id),
    onSuccess: () => {
      toast.success(t("compliance.deleted"));
      setEditingId(null);
      setForm(emptyForm);
      void queryClient.invalidateQueries({ queryKey: ["compliance-templates"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const templates = templatesQuery.data?.items ?? [];
  const groups = (groupsQuery.data?.groups ?? []).filter((item) => item.state === "applied");
  const summary = reportQuery.data?.summary;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><Scale className="h-3.5 w-3.5 text-primary" />{t("nav.operations")}</>}
        title={t("nav.compliance")}
        description={t("compliance.subtitle")}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("compliance.templates")}</CardTitle>
          <CardDescription>{t("compliance.templatesDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="divide-y">
            {templates.map((template) => (
              <div key={template.id} className="flex items-center justify-between gap-3 py-2 text-xs">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{template.name}</span>
                    <Badge variant="outline">
                      {template.scope_type === "global"
                        ? t("compliance.scopeGlobal")
                        : `${template.scope_type}: ${template.scope_value}`}
                    </Badge>
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {t("compliance.lines", { count: template.content.split("\n").length })}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {can("compliance.write") ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingId(template.id);
                        setForm({
                          name: template.name,
                          scope_type: template.scope_type,
                          scope_value: template.scope_value ?? "",
                          content: template.content,
                        });
                      }}
                    >
                      {t("common.edit")}
                    </Button>
                  ) : null}
                  {can("compliance.write") ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => remove.mutate(template.id)}
                    >
                      <Trash2 />
                      {t("common.delete")}
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
            {!templates.length ? (
              <p className="py-2 text-xs text-muted-foreground">{t("compliance.noTemplates")}</p>
            ) : null}
          </div>

          {can("compliance.write") ? (
            <div className="space-y-3 rounded-md border bg-muted/10 p-3">
              <div className="flex flex-wrap items-end gap-2">
                <div className="space-y-1">
                  <Label>{t("compliance.name")}</Label>
                  <Input
                    value={form.name}
                    maxLength={100}
                    onChange={(event) => setForm({ ...form, name: event.target.value })}
                    className="w-52"
                  />
                </div>
                <div className="space-y-1">
                  <Label>{t("compliance.scope")}</Label>
                  <Select
                    value={form.scope_type}
                    onValueChange={(value) =>
                      setForm({ ...form, scope_type: value as ConfigTemplate["scope_type"], scope_value: "" })
                    }
                  >
                    <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="global">{t("compliance.scopeGlobal")}</SelectItem>
                      <SelectItem value="group">{t("compliance.scopeGroup")}</SelectItem>
                      <SelectItem value="model">{t("compliance.scopeModel")}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {form.scope_type !== "global" ? (
                  <div className="space-y-1">
                    <Label>{t("compliance.scopeValue")}</Label>
                    <Input
                      value={form.scope_value}
                      onChange={(event) => setForm({ ...form, scope_value: event.target.value })}
                      placeholder={form.scope_type === "group" ? "core" : "ios"}
                      className="w-40"
                    />
                  </div>
                ) : null}
                <Button
                  type="button"
                  size="sm"
                  disabled={save.isPending || !form.name.trim() || !form.content.trim()}
                  onClick={() => save.mutate()}
                >
                  {save.isPending ? <Spinner /> : <Plus />}
                  {editingId ? t("compliance.update") : t("compliance.addTemplate")}
                </Button>
                {editingId ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setEditingId(null);
                      setForm(emptyForm);
                    }}
                  >
                    {t("common.cancel")}
                  </Button>
                ) : null}
              </div>
              <textarea
                value={form.content}
                onChange={(event) => setForm({ ...form, content: event.target.value })}
                placeholder={t("compliance.contentPlaceholder")}
                spellCheck={false}
                className="min-h-[160px] w-full rounded-md border bg-card px-3 py-2 font-mono text-[11px] leading-relaxed outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-start justify-between space-y-0">
          <div>
            <CardTitle className="text-sm">{t("compliance.report")}</CardTitle>
            <CardDescription>{t("compliance.reportDescription")}</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={group} onValueChange={setGroup}>
              <SelectTrigger className="h-8 w-40 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{t("compliance.allGroups")}</SelectItem>
                {groups.map((item) => (
                  <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={templateFilter} onValueChange={setTemplateFilter}>
              <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__auto__">{t("compliance.autoTemplate")}</SelectItem>
                {templates.map((template) => (
                  <SelectItem key={template.id} value={String(template.id)}>{template.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="outline" size="sm" onClick={() => void reportQuery.refetch()} disabled={reportQuery.isFetching}>
              {reportQuery.isFetching ? <Spinner /> : <Scale />}
              {t("compliance.evaluate")}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {summary ? (
            <div className="flex flex-wrap gap-2 text-[11px]">
              <Badge variant="success"><CheckCircle2 className="h-3 w-3" />{t("compliance.compliant")}: {summary.compliant}</Badge>
              <Badge variant="destructive"><XCircle className="h-3 w-3" />{t("compliance.deviating")}: {summary.deviating}</Badge>
              <Badge variant="warning"><TriangleAlert className="h-3 w-3" />{t("compliance.errors")}: {summary.error}</Badge>
              <Badge variant="outline"><FileWarning className="h-3 w-3" />{t("compliance.noTemplate")}: {summary.no_template}</Badge>
            </div>
          ) : null}

          {reportQuery.isLoading ? (
            <div className="h-24 animate-pulse rounded-md bg-muted" />
          ) : !(reportQuery.data?.items ?? []).length ? (
            <EmptyState icon={Scale} title={t("compliance.emptyTitle")} description={t("compliance.emptyDescription")} compact />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("nodes.name")}</TableHead>
                  <TableHead>{t("nodes.group")}</TableHead>
                  <TableHead>{t("compliance.template")}</TableHead>
                  <TableHead>{t("common.status")}</TableHead>
                  <TableHead className="text-right">{t("compliance.changes")}</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(reportQuery.data?.items ?? []).map((item) => (
                  <TableRow key={item.node_id}>
                    <TableCell className="text-[13px] font-medium">{item.name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.group_name ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{item.template_name ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariants[item.status]}>{t(`compliance.status.${item.status}`)}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-[10px] text-muted-foreground">
                      {item.additions || item.deletions ? `+${item.additions} / -${item.deletions}` : "—"}
                    </TableCell>
                    <TableCell>
                      {item.template_id ? (
                        <Button variant="ghost" size="sm" onClick={() => setOpenNode(item.node_id)}>
                          {t("compliance.viewDiff")}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Dialog open={openNode !== null} onOpenChange={(open) => !open && setOpenNode(null)}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>{t("compliance.diffTitle", { name: nodeReportQuery.data?.name ?? "" })}</DialogTitle>
            <DialogDescription>
              {t("compliance.diffDescription", { template: nodeReportQuery.data?.template.name ?? "" })}
            </DialogDescription>
          </DialogHeader>
          {nodeReportQuery.isLoading ? (
            <div className="h-40 animate-pulse rounded-md bg-muted" />
          ) : nodeReportQuery.data ? (
            <DiffView
              diff={nodeReportQuery.data.diff}
              fromLabel={t("compliance.template")}
              toLabel={t("compliance.currentConfig")}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
