import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CopyPlus, Pencil, Plus, Server, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { KeyValueEditor } from "@/components/shared/key-value-editor";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { notifyError } from "@/lib/errors";
import type { NodeTemplate } from "@/types/api";

type FormState = Omit<NodeTemplate, "id" | "created_at" | "updated_at">;

const emptyForm: FormState = {
  name: "",
  model: "",
  group_name: null,
  input: "ssh",
  port: 22,
  username: "",
  output: null,
  prompt: null,
  timeout_seconds: null,
  vars: {},
};

export function NodeTemplatesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [applyTarget, setApplyTarget] = useState<NodeTemplate | null>(null);
  const [applyName, setApplyName] = useState("");
  const [applyAddress, setApplyAddress] = useState("");
  usePageTitle("nav.nodeTemplates");

  const templatesQuery = useQuery({ queryKey: ["node-templates"], queryFn: api.nodeTemplates });
  const groupsQuery = useQuery({ queryKey: ["groups"], queryFn: api.groups });

  const save = useMutation({
    mutationFn: () =>
      editingId
        ? api.updateNodeTemplate(editingId, form)
        : api.createNodeTemplate(form),
    onSuccess: () => {
      toast.success(t("templates.saved"));
      setEditingId(null);
      setForm(emptyForm);
      void queryClient.invalidateQueries({ queryKey: ["node-templates"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteNodeTemplate(id),
    onSuccess: () => {
      toast.success(t("templates.deleted"));
      void queryClient.invalidateQueries({ queryKey: ["node-templates"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const apply = useMutation({
    mutationFn: () =>
      api.applyNodeTemplate(applyTarget!.id, {
        name: applyName.trim(),
        address: applyAddress.trim() || null,
      }),
    onSuccess: (result) => {
      toast.success(t("templates.applied", { name: result.node.name }));
      setApplyTarget(null);
      setApplyName("");
      setApplyAddress("");
      void queryClient.invalidateQueries({ queryKey: ["nodes"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const groups = (groupsQuery.data?.groups ?? []).filter((group) => group.state === "applied");
  const templates = templatesQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><Server className="h-3.5 w-3.5 text-primary" />{t("nav.inventory")}</>}
        title={t("nav.nodeTemplates")}
        description={t("templates.subtitle")}
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("templates.list")}</CardTitle>
          <CardDescription>{t("templates.listDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {templates.length ? (
            <div className="divide-y">
              {templates.map((template) => (
                <div key={template.id} className="flex flex-wrap items-center justify-between gap-3 py-2 text-xs">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{template.name}</span>
                      <Badge variant="outline">{template.model}</Badge>
                      {template.group_name ? <Badge variant="secondary">{template.group_name}</Badge> : null}
                      {template.input ? <span className="text-muted-foreground">{template.input}</span> : null}
                      {template.port ? <span className="font-mono text-muted-foreground">:{template.port}</span> : null}
                    </p>
                    {template.username ? (
                      <p className="font-mono text-[10px] text-muted-foreground">{template.username}</p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1">
                    <Button variant="outline" size="sm" onClick={() => { setApplyTarget(template); setApplyName(""); setApplyAddress(""); }}>
                      <CopyPlus />
                      {t("templates.use")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      title={t("common.edit")}
                      onClick={() => {
                        setEditingId(template.id);
                        setForm({
                          name: template.name,
                          model: template.model,
                          group_name: template.group_name,
                          input: template.input,
                          port: template.port,
                          username: template.username,
                          output: template.output,
                          prompt: template.prompt,
                          timeout_seconds: template.timeout_seconds,
                          vars: template.vars ?? {},
                        });
                      }}
                    >
                      <Pencil />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-muted-foreground hover:text-destructive"
                      title={t("common.delete")}
                      onClick={() => remove.mutate(template.id)}
                    >
                      <Trash2 />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{t("templates.empty")}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{editingId ? t("templates.editTitle") : t("templates.createTitle")}</CardTitle>
          <CardDescription>{t("templates.createDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1">
              <Label>{t("templates.name")}</Label>
              <Input value={form.name} maxLength={100} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>{t("templates.model")}</Label>
              <Input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} placeholder="ios" />
            </div>
            <div className="space-y-1">
              <Label>{t("templates.group")}</Label>
              <Select
                value={form.group_name ?? "__none__"}
                onValueChange={(value) => setForm({ ...form, group_name: value === "__none__" ? null : value })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{t("templates.noGroup")}</SelectItem>
                  {groups.map((group) => (
                    <SelectItem key={group.name} value={group.name}>{group.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>{t("templates.input")}</Label>
              <Input value={form.input ?? ""} onChange={(event) => setForm({ ...form, input: event.target.value || null })} placeholder="ssh" />
            </div>
            <div className="space-y-1">
              <Label>{t("templates.port")}</Label>
              <Input
                type="number"
                min={1}
                max={65535}
                value={form.port ?? ""}
                onChange={(event) => setForm({ ...form, port: event.target.value ? Number(event.target.value) : null })}
              />
            </div>
            <div className="space-y-1">
              <Label>{t("templates.username")}</Label>
              <Input value={form.username ?? ""} onChange={(event) => setForm({ ...form, username: event.target.value || null })} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>{t("templates.vars")}</Label>
            <KeyValueEditor value={form.vars} onChange={(vars) => setForm({ ...form, vars })} addLabel={t("nodeForm.addVar")} />
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" disabled={save.isPending || !form.name.trim() || !form.model.trim()} onClick={() => save.mutate()}>
              {save.isPending ? <Spinner /> : <Plus />}
              {editingId ? t("templates.update") : t("templates.create")}
            </Button>
            {editingId ? (
              <Button
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
        </CardContent>
      </Card>

      <Dialog open={Boolean(applyTarget)} onOpenChange={(open) => !open && setApplyTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("templates.applyTitle", { name: applyTarget?.name ?? "" })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>{t("nodes.name")}</Label>
              <Input value={applyName} onChange={(event) => setApplyName(event.target.value)} placeholder="core-sw-02" />
            </div>
            <div className="space-y-1">
              <Label>{t("nodes.address")}</Label>
              <Input value={applyAddress} onChange={(event) => setApplyAddress(event.target.value)} placeholder="10.0.0.2" />
            </div>
            <p className="text-[11px] text-muted-foreground">{t("templates.applyHelp")}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setApplyTarget(null)}>{t("common.cancel")}</Button>
            <Button disabled={!applyName.trim() || apply.isPending} onClick={() => apply.mutate()}>
              {apply.isPending ? <Spinner /> : <CopyPlus />}
              {t("templates.createNode")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
