import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  KeyRound,
  LockKeyhole,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  TriangleAlert,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { AutocompleteInput } from "@/components/shared/autocomplete-input";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { KeyValueEditor } from "@/components/shared/key-value-editor";
import { KnownVariables } from "@/components/shared/known-variables";
import { Spinner, TableSkeleton } from "@/components/shared/loaders";
import { PageHeader } from "@/components/shared/page-header";
import { PasswordInput } from "@/components/shared/password-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, notifyError } from "@/lib/errors";
import { groupSchema } from "@/lib/validation";
import type { CatalogVar, Group, GroupInput, GroupModelOverride } from "@/types/api";

type SecretMode = "keep" | "replace" | "clear";

interface GroupFormValues {
  name: string;
  username: string;
}

interface OverrideRow {
  id: number;
  name: string;
  username: string;
  password: string;
  enable: string;
  passwordMode: SecretMode;
  enableMode: SecretMode;
  hasPassword: boolean;
  hasEnable: boolean;
  vars: Record<string, unknown>;
}

function SecretField({
  label,
  existing,
  mode,
  setMode,
  value,
  setValue,
}: {
  label: string;
  existing: boolean;
  mode: SecretMode;
  setMode: (mode: SecretMode) => void;
  value: string;
  setValue: (value: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {existing ? (
        <Select value={mode} onValueChange={(next) => setMode(next as SecretMode)}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="keep">{t("common.keep")}</SelectItem>
            <SelectItem value="replace">{t("common.replace")}</SelectItem>
            <SelectItem value="clear">{t("common.clear")}</SelectItem>
          </SelectContent>
        </Select>
      ) : null}
      {mode === "replace" ? <PasswordInput value={value} onChange={(event) => setValue(event.target.value)} autoComplete="new-password" /> : null}
      {mode === "keep" && existing ? <p className="rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs text-muted-foreground">••••••••</p> : null}
      {mode === "clear" && existing ? <p className="text-xs text-destructive">{t("common.clear")}</p> : null}
    </div>
  );
}

function GroupFormDialog({
  open,
  onOpenChange,
  group,
  models,
  variables,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: Group | null;
  models: string[];
  variables: CatalogVar[];
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [passwordMode, setPasswordMode] = useState<SecretMode>(group ? "keep" : "replace");
  const [enableMode, setEnableMode] = useState<SecretMode>(group ? "keep" : "replace");
  const [password, setPassword] = useState("");
  const [enable, setEnable] = useState("");
  const [vars, setVars] = useState<Record<string, unknown>>(group?.vars ?? {});
  const [overrides, setOverrides] = useState<OverrideRow[]>(() =>
    Object.entries(group?.models ?? {}).map(([name, override], index) => ({
      id: index,
      name,
      username: override.username ?? "",
      password: "",
      enable: "",
      passwordMode: "keep",
      enableMode: "keep",
      hasPassword: Boolean(override.has_password),
      hasEnable: Boolean(override.has_enable),
      vars: override.vars ?? {},
    })),
  );
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [removedModels, setRemovedModels] = useState<string[]>([]);

  const form = useForm<GroupFormValues>({
    resolver: zodResolver(groupSchema(t)) as never,
    defaultValues: { name: group?.name ?? "", username: group?.username ?? "" },
  });

  useEffect(() => {
    form.reset({ name: group?.name ?? "", username: group?.username ?? "" });
    setPasswordMode(group ? "keep" : "replace");
    setEnableMode(group ? "keep" : "replace");
    setVars(group?.vars ?? {});
    setOverrides(
      Object.entries(group?.models ?? {}).map(([name, override], index) => ({
        id: index,
        name,
        username: override.username ?? "",
        password: "",
        enable: "",
        passwordMode: "keep",
        enableMode: "keep",
        hasPassword: Boolean(override.has_password),
        hasEnable: Boolean(override.has_enable),
        vars: override.vars ?? {},
      })),
    );
    setPassword("");
    setEnable("");
    setRemovedModels([]);
    setServerError(null);
  }, [group, form, open]);

  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    setSubmitting(true);
    try {
      const modelPayload: Record<string, GroupModelOverride> = {};
      overrides.forEach((override) => {
        if (!override.name.trim()) return;
        modelPayload[override.name.trim()] = {
          username: override.username.trim() || null,
          vars: override.vars,
          clear_password: override.passwordMode === "clear",
          clear_enable: override.enableMode === "clear",
          ...(override.passwordMode === "replace" && override.password ? { password: override.password } : {}),
          ...(override.enableMode === "replace" && override.enable ? { enable: override.enable } : {}),
        };
      });
      removedModels.forEach((modelName) => {
        modelPayload[modelName] = { remove: true };
      });
      const payload: GroupInput = {
        username: values.username.trim() || null,
        vars,
        models: modelPayload,
        clear_password: passwordMode === "clear",
        clear_enable: enableMode === "clear",
        ...(passwordMode === "replace" && password ? { password } : {}),
        ...(enableMode === "replace" && enable ? { enable } : {}),
      };
      if (group) {
        await api.updateGroup(group.name, payload);
      } else {
        await api.createGroup({ ...payload, name: values.name.trim() });
      }
      toast.success(t("groups.savedDraft"));
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      onSaved();
      onOpenChange(false);
    } catch (error) {
      setServerError(errorMessage(t, error));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{group ? t("groups.editTitle") : t("groups.createTitle")}</DialogTitle>
          <DialogDescription>{group ? t("groups.editDescription") : t("groups.createDescription")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-6" noValidate>
          {serverError ? (
            <div className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {serverError}
            </div>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="group-name">{t("groups.groupName")}</Label>
              <Input id="group-name" disabled={Boolean(group)} autoFocus={!group} {...form.register("name")} />
              {form.formState.errors.name ? <p className="text-xs text-destructive">{form.formState.errors.name.message}</p> : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-username">{t("groups.username")}</Label>
              <Input id="group-username" autoComplete="off" {...form.register("username")} />
            </div>
            <SecretField
              label={t("groups.password")}
              existing={Boolean(group?.has_password)}
              mode={passwordMode}
              setMode={setPasswordMode}
              value={password}
              setValue={setPassword}
            />
            <SecretField
              label={t("groups.enable")}
              existing={Boolean(group?.has_enable)}
              mode={enableMode}
              setMode={setEnableMode}
              value={enable}
              setValue={setEnable}
            />
          </div>

          <div className="space-y-2 border-t pt-5">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{t("groups.vars")}</h3>
              <p className="mt-1 text-[11px] text-muted-foreground">{t("groups.varsHelp")}</p>
            </div>
            <KeyValueEditor
              value={vars}
              onChange={setVars}
              addLabel={t("groups.addVar")}
              suggestions={variables.map((variable) => variable.name)}
            />
            <KnownVariables variables={variables} />
          </div>

          <div className="space-y-3 border-t pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">{t("groups.modelOverrides")}</h3>
                <p className="mt-1 text-[11px] text-muted-foreground">{t("groups.modelOverridesHelp")}</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  setOverrides((current) => [
                    ...current,
                    {
                      id: Date.now(),
                      name: "",
                      username: "",
                      password: "",
                      enable: "",
                      passwordMode: "replace",
                      enableMode: "replace",
                      hasPassword: false,
                      hasEnable: false,
                      vars: {},
                    },
                  ])
                }
              >
                <Plus />
                {t("groups.addModel")}
              </Button>
            </div>
            {overrides.length === 0 ? (
              <p className="rounded-md border border-dashed px-3 py-4 text-xs text-muted-foreground">{t("groups.noModels")}</p>
            ) : (
              <div className="space-y-3">
                {overrides.map((override) => (
                  <div key={override.id} className="rounded-lg border bg-muted/15 p-3">
                    <div className="mb-3 flex items-end gap-2">
                      <div className="min-w-0 flex-1 space-y-1">
                        <Label>{t("groups.model")}</Label>
                        <AutocompleteInput
                          suggestions={models}
                          value={override.name}
                          onChange={(event) => {
                            const nextName = event.target.value;
                            setRemovedModels((current) => current.filter((name) => name !== nextName));
                            setOverrides((current) =>
                              current.map((item) => (item.id === override.id ? { ...item, name: nextName } : item)),
                            );
                          }}
                          className="h-8 font-mono text-xs"
                        />
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        onClick={() => {
                          if (group?.models[override.name]) {
                            setRemovedModels((current) =>
                              current.includes(override.name) ? current : [...current, override.name],
                            );
                          }
                          setOverrides((current) => current.filter((item) => item.id !== override.id));
                        }}
                        aria-label={t("common.remove")}
                      >
                        <X />
                      </Button>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="space-y-1">
                        <Label>{t("groups.username")}</Label>
                        <Input
                          value={override.username}
                          onChange={(event) =>
                            setOverrides((current) =>
                              current.map((item) => (item.id === override.id ? { ...item, username: event.target.value } : item)),
                            )
                          }
                          className="h-8"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label>{t("groups.password")}</Label>
                        {override.hasPassword ? (
                          <Select
                            value={override.passwordMode}
                            onValueChange={(value) =>
                              setOverrides((current) =>
                                current.map((item) =>
                                  item.id === override.id ? { ...item, passwordMode: value as SecretMode } : item,
                                ),
                              )
                            }
                          >
                            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="keep">{t("common.keep")}</SelectItem>
                              <SelectItem value="replace">{t("common.replace")}</SelectItem>
                              <SelectItem value="clear">{t("common.clear")}</SelectItem>
                            </SelectContent>
                          </Select>
                        ) : null}
                        {override.passwordMode === "replace" ? (
                          <PasswordInput
                            value={override.password}
                            onChange={(event) =>
                              setOverrides((current) =>
                                current.map((item) => (item.id === override.id ? { ...item, password: event.target.value } : item)),
                              )
                            }
                            className="h-8"
                          />
                        ) : null}
                      </div>
                      <div className="space-y-1">
                        <Label>{t("groups.enable")}</Label>
                        {override.hasEnable ? (
                          <Select
                            value={override.enableMode}
                            onValueChange={(value) =>
                              setOverrides((current) =>
                                current.map((item) =>
                                  item.id === override.id ? { ...item, enableMode: value as SecretMode } : item,
                                ),
                              )
                            }
                          >
                            <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="keep">{t("common.keep")}</SelectItem>
                              <SelectItem value="replace">{t("common.replace")}</SelectItem>
                              <SelectItem value="clear">{t("common.clear")}</SelectItem>
                            </SelectContent>
                          </Select>
                        ) : null}
                        {override.enableMode === "replace" ? (
                          <PasswordInput
                            value={override.enable}
                            onChange={(event) =>
                              setOverrides((current) =>
                                current.map((item) => (item.id === override.id ? { ...item, enable: event.target.value } : item)),
                              )
                            }
                            className="h-8"
                          />
                        ) : null}
                      </div>
                    </div>
                    <div className="mt-3 space-y-1">
                      <Label>{t("groups.vars")}</Label>
                      <KeyValueEditor
                        value={override.vars}
                        onChange={(vars) =>
                          setOverrides((current) =>
                            current.map((item) => (item.id === override.id ? { ...item, vars } : item)),
                          )
                        }
                        addLabel={t("groups.addVar")}
                        suggestions={variables.map((variable) => variable.name)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? <Spinner /> : <Check />}
              {submitting ? t("common.saving") : t("groups.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function GroupsPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Group | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Group | null>(null);
  const [pageStatus, setPageStatus] = useState<string | null>(null);
  usePageTitle("nav.groups");

  const groupsQuery = useQuery({ queryKey: ["groups"], queryFn: api.groups });
  const catalogQuery = useQuery({ queryKey: ["config-catalog"], queryFn: api.configCatalog, staleTime: 5 * 60_000 });

  const remove = useMutation({
    mutationFn: (group: Group) => api.deleteGroup(group.name),
    onSuccess: () => {
      toast.success(t("groups.deletedDraft"));
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
      void queryClient.invalidateQueries({ queryKey: ["config"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };
  const openEdit = (group: Group) => {
    setEditing(group);
    setFormOpen(true);
  };

  const groups = groupsQuery.data?.groups ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <UsersRound className="h-3.5 w-3.5 text-primary" />
            {t("nav.inventory")}
          </>
        }
        title={t("groups.title")}
        description={t("groups.subtitle")}
        actions={
          <>
            {can("config.read") ? (
              <Button variant="outline" size="sm" asChild>
                <Link to="/config">
                  {t("groups.applyNow")}
                  <ArrowRight />
                </Link>
              </Button>
            ) : null}
            <Button size="sm" onClick={openCreate}>
              <Plus />
              {t("groups.addGroup")}
            </Button>
          </>
        }
      />

      {groupsQuery.data?.requires_admin_apply ? (
        <div className="flex flex-col gap-3 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <div>
              <p className="font-medium text-warning">{t("groups.requiresApply")}</p>
              <p className="mt-0.5 text-muted-foreground">{t("groups.requiresApplyDescription")}</p>
            </div>
          </div>
          {can("config.read") ? (
            <Button variant="outline" size="sm" asChild>
              <Link to="/config">{t("groups.applyNow")}</Link>
            </Button>
          ) : null}
        </div>
      ) : null}

      {pageStatus ? <p className="text-sm text-muted-foreground">{pageStatus}</p> : null}

      {groupsQuery.isLoading ? (
        <div className="rounded-lg border bg-card p-2"><TableSkeleton rows={5} columns={5} /></div>
      ) : groupsQuery.isError ? (
        <ErrorState onRetry={() => void groupsQuery.refetch()} />
      ) : groups.length === 0 ? (
        <EmptyState
          icon={UsersRound}
          title={t("groups.emptyTitle")}
          description={t("groups.emptyDescription")}
          action={<Button onClick={openCreate}><Plus />{t("groups.addGroup")}</Button>}
        />
      ) : (
        <div className="overflow-hidden rounded-lg border bg-card shadow-soft">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("groups.name")}</TableHead>
                <TableHead>{t("groups.nodeCount")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("groups.credentials")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("groups.vars")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {groups.map((group) => (
                <TableRow key={group.name}>
                  <TableCell>
                    <button type="button" onClick={() => openEdit(group)} className="flex items-center gap-2.5 text-left">
                      <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-muted/20 text-muted-foreground">
                        <UsersRound className="h-3.5 w-3.5" />
                      </span>
                      <span>
                        <span className="block text-[13px] font-medium hover:text-primary">{group.name}</span>
                        <span className="block font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground">
                          {Object.keys(group.models).length} {t("groups.models").toLowerCase()}
                        </span>
                      </span>
                    </button>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{group.node_count}</TableCell>
                  <TableCell className="hidden lg:table-cell">
                    <span className="flex flex-wrap gap-1">
                      {group.has_password ? <Badge variant="success"><KeyRound />{t("groups.password")}</Badge> : null}
                      {group.has_enable ? <Badge variant="info"><LockKeyhole />{t("groups.enable")}</Badge> : null}
                      {!group.has_password && !group.has_enable ? <span className="text-xs text-muted-foreground">—</span> : null}
                    </span>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs text-muted-foreground md:table-cell">
                    {Object.keys(group.vars).length}
                  </TableCell>
                  <TableCell>
                    {group.draft ? (
                      <Badge variant="warning">{t("groups.draft")}</Badge>
                    ) : (
                      <Badge variant="success">{t("groups.applied")}</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-xs" aria-label={t("common.more")}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => openEdit(group)}><Pencil />{t("common.edit")}</DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onSelect={() => setDeleteTarget(group)}
                          disabled={group.node_count > 0}
                        >
                          <Trash2 />{t("common.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <GroupFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        group={editing}
        models={catalogQuery.data?.models ?? []}
        variables={catalogQuery.data?.vars ?? []}
        onSaved={() => setPageStatus(null)}
      />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("groups.deleteTitle")}
        description={t("groups.deleteDescription", { name: deleteTarget?.name ?? "" })}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget)}
      />
    </div>
  );
}
