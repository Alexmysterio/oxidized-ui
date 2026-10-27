import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, KeyRound, Save, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { KeyValueEditor } from "@/components/shared/key-value-editor";
import { KnownVariables } from "@/components/shared/known-variables";
import { ModelCombobox } from "@/components/shared/model-combobox";
import { PasswordInput } from "@/components/shared/password-input";
import { Spinner } from "@/components/shared/loaders";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SheetFooter, SheetHeader } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { nodeSchema } from "@/lib/validation";
import type { CatalogVar, Group, Node, NodeInput } from "@/types/api";

type SecretMode = "keep" | "replace" | "clear";

interface FormValues {
  name: string;
  address: string;
  model: string;
  group_name: string;
  input: string;
  port: number | typeof NaN;
  username: string;
  output: string;
  prompt: string;
  timeout_seconds: number | typeof NaN;
}

function toFormValues(node: Node | null): FormValues {
  return {
    name: node?.name ?? "",
    address: node?.address ?? "",
    model: node?.model ?? "",
    group_name: node?.group_name ?? "__none__",
    input: node?.input ?? "",
    port: node?.port ?? Number.NaN,
    username: node?.username ?? "",
    output: node?.output ?? "",
    prompt: node?.prompt ?? "",
    timeout_seconds: node?.timeout_seconds ?? Number.NaN,
  };
}

function SecretControl({
  title,
  help,
  hasSecret,
  mode,
  setMode,
  value,
  setValue,
  modeLabels,
  disabled,
}: {
  title: string;
  help: string;
  hasSecret: boolean;
  mode: SecretMode;
  setMode: (mode: SecretMode) => void;
  value: string;
  setValue: (value: string) => void;
  modeLabels: { keep: string; replace: string; clear: string };
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        <Label>{title}</Label>
        <p className="text-xs leading-relaxed text-muted-foreground">{help}</p>
      </div>
      {hasSecret ? (
        <Select value={mode} onValueChange={(value) => setMode(value as SecretMode)} disabled={disabled}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="keep">{modeLabels.keep}</SelectItem>
            <SelectItem value="replace">{modeLabels.replace}</SelectItem>
            <SelectItem value="clear">{modeLabels.clear}</SelectItem>
          </SelectContent>
        </Select>
      ) : null}
      {mode === "replace" ? (
        <PasswordInput
          value={value}
          onChange={(event) => setValue(event.target.value)}
          autoComplete="new-password"
          placeholder={hasSecret ? t("nodeForm.secretReplaceHint") : undefined}
          aria-label={title}
        />
      ) : null}
      {mode === "clear" ? (
        <p className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          <TriangleAlert className="h-3.5 w-3.5" />
          {modeLabels.clear}
        </p>
      ) : null}
      {mode === "keep" && hasSecret ? (
        <p className="rounded-md border bg-muted/30 px-3 py-2 font-mono text-xs text-muted-foreground">••••••••••••</p>
      ) : null}
    </div>
  );
}

function NodeForm({
  node,
  groups,
  models,
  modelVendors,
  inputs,
  outputs,
  variables,
  tagKeySuggestions,
  tagValueSuggestions,
  onSaved,
  onCancel,
}: {
  node: Node | null;
  groups: Group[];
  models: string[];
  modelVendors: Record<string, string>;
  inputs: string[];
  outputs: string[];
  variables: CatalogVar[];
  tagKeySuggestions: string[];
  tagValueSuggestions: Record<string, string[]>;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [vars, setVars] = useState<Record<string, unknown>>(node?.vars ?? {});
  const [tags, setTags] = useState<Record<string, unknown>>(node?.tags ?? {});
  const [passwordMode, setPasswordMode] = useState<SecretMode>(node ? "keep" : "replace");
  const [enableMode, setEnableMode] = useState<SecretMode>(node ? "keep" : "replace");
  const [password, setPassword] = useState("");
  const [enable, setEnable] = useState("");
  const [trustFirstKey, setTrustFirstKey] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const isEdit = Boolean(node);

  const form = useForm<FormValues>({
    resolver: zodResolver(nodeSchema(t)) as never,
    defaultValues: toFormValues(node),
  });

  useEffect(() => {
    form.reset(toFormValues(node));
    setVars(node?.vars ?? {});
    setTags(node?.tags ?? {});
  }, [node, form]);

  const appliedGroups = groups.filter((group) => group.state === "applied" || group.name === node?.group_name);

  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    setSubmitting(true);
    try {
      const payload: NodeInput = {
        name: values.name.trim(),
        model: values.model.trim(),
        address: values.address.trim() || null,
        group_name: values.group_name === "__none__" ? null : values.group_name || null,
        input: values.input.trim() || null,
        port: Number.isNaN(values.port) ? null : Number(values.port),
        username: values.username.trim() || null,
        vars,
        tags: Object.fromEntries(
          Object.entries(tags)
            .map(([key, value]) => [key, String(value).trim()] as const)
            .filter(([key, value]) => key.trim() && value),
        ),
        output: values.output.trim() || null,
        prompt: values.prompt.trim() || null,
        timeout_seconds: Number.isNaN(values.timeout_seconds) ? null : Number(values.timeout_seconds),
        clear_password: passwordMode === "clear",
        clear_enable: enableMode === "clear",
      };
      if (passwordMode === "replace" && password) payload.password = password;
      if (enableMode === "replace" && enable) payload.enable = enable;
      if (!node) {
        delete payload.clear_password;
        delete payload.clear_enable;
      }

      const result = node
        ? await api.updateNode(node.id, payload)
        : await api.createNode({ ...payload, name: values.name.trim() });

      if (!node && trustFirstKey) {
        try {
          const trusted = await api.trustHostKey(result.node.id);
          toast.success(t("nodeForm.hostKeyTrusted", { fingerprint: trusted.fingerprints[0] ?? "—" }));
        } catch (error) {
          toast.warning(t("nodeForm.hostKeyTrustFailed"), {
            description: errorMessage(t, error),
          });
        }
      }

      if (result.reload_status !== "ok" && result.reload_status !== "recovered") {
        toast.warning(t("nodes.reloadFailed"), {
          description: result.warnings.map((warning) => t(`errors.${warning}`, { defaultValue: warning })).join("\n"),
        });
      }
      toast.success(node ? t("nodeForm.updated") : t("nodeForm.created"));
      await queryClient.invalidateQueries({ queryKey: ["nodes"] });
      await queryClient.invalidateQueries({ queryKey: ["status"] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
      onSaved();
    } catch (error) {
      setServerError(errorMessage(t, error));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col" noValidate>
      <div className="min-h-0 flex-1 space-y-7 overflow-y-auto px-6 py-5">
        {serverError ? (
          <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {serverError}
          </div>
        ) : null}

        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border bg-muted/40 font-mono text-[10px] text-muted-foreground">
              01
            </span>
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("nodeForm.identity")}
            </h3>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="node-name">{t("nodeForm.name")}</Label>
              <Input id="node-name" autoFocus placeholder={t("nodeForm.namePlaceholder")} aria-invalid={Boolean(form.formState.errors.name)} {...form.register("name")} />
              {form.formState.errors.name ? (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              ) : (
                <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.nameHelp")}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="node-address">{t("nodeForm.address")}</Label>
              <Input id="node-address" placeholder={t("nodeForm.addressPlaceholder")} {...form.register("address")} />
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.addressHelp")}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="node-model">{t("nodeForm.model")}</Label>
              <ModelCombobox
                id="node-model"
                value={form.watch("model")}
                onChange={(value) => form.setValue("model", value, { shouldDirty: true, shouldValidate: true })}
                models={models}
                vendors={modelVendors}
                invalid={Boolean(form.formState.errors.model)}
                ariaDescribedBy={form.formState.errors.model ? undefined : "node-model-help"}
              />
              {form.formState.errors.model ? (
                <p className="text-xs text-destructive">{form.formState.errors.model.message}</p>
              ) : (
                <p id="node-model-help" className="text-[11px] leading-relaxed text-muted-foreground">
                  {t("nodeForm.modelHelp")}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label>{t("nodeForm.group")}</Label>
              <Select
                value={form.watch("group_name") || "__none__"}
                onValueChange={(value) => form.setValue("group_name", value, { shouldDirty: true })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">{t("nodeForm.noGroup")}</SelectItem>
                  {appliedGroups.map((group) => (
                    <SelectItem key={group.name} value={group.name}>
                      {group.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.groupHelp")}</p>
            </div>
          </div>
        </section>

        <section className="space-y-4 border-t pt-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border bg-muted/40 font-mono text-[10px] text-muted-foreground">
              02
            </span>
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("nodeForm.connection")}
            </h3>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="node-input">{t("nodeForm.input")}</Label>
              <Input id="node-input" list="node-inputs" placeholder={t("nodeForm.inputPlaceholder")} {...form.register("input")} />
              <datalist id="node-inputs">
                {inputs.map((input) => (
                  <option key={input} value={input} />
                ))}
              </datalist>
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.inputHelp")}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="node-port">{t("nodeForm.port")}</Label>
              <Input
                id="node-port"
                type="number"
                min={1}
                max={65535}
                aria-invalid={Boolean(form.formState.errors.port)}
                {...form.register("port", { valueAsNumber: true })}
              />
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.portHelp")}</p>
            </div>
          </div>
          {!node ? (
            <div className="flex items-start gap-2.5 rounded-md border bg-muted/20 p-3">
              <Checkbox
                id="trust-first-key"
                checked={trustFirstKey}
                onCheckedChange={(value) => setTrustFirstKey(value === true)}
                className="mt-0.5"
              />
              <label htmlFor="trust-first-key" className="min-w-0 cursor-pointer">
                <span className="block text-xs font-medium">{t("nodeForm.trustFirstKey")}</span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
                  {t("nodeForm.trustFirstKeyHelp")}
                </span>
              </label>
            </div>
          ) : null}
        </section>

        <section className="space-y-4 border-t pt-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border bg-muted/40 font-mono text-[10px] text-muted-foreground">
              03
            </span>
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("nodeForm.credentials")}
            </h3>
          </div>
          <div className="space-y-2">
            <Label htmlFor="node-username">{t("nodeForm.username")}</Label>
            <Input id="node-username" autoComplete="off" {...form.register("username")} />
            {node?.effective?.username?.value && node.effective.username.source !== "node" ? (
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {t("nodeForm.inheritedUsername", {
                  value: node.effective.username.value,
                  source: t(`nodeDetail.sources.${node.effective.username.source}`, {
                    defaultValue: node.effective.username.source,
                  }),
                })}
              </p>
            ) : null}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <SecretControl
              title={t("nodeForm.password")}
              help={t("nodeForm.passwordHelp")}
              hasSecret={Boolean(node?.has_password)}
              mode={passwordMode}
              setMode={setPasswordMode}
              value={password}
              setValue={setPassword}
              modeLabels={{
                keep: t("nodeForm.passwordKeep"),
                replace: t("nodeForm.passwordReplace"),
                clear: t("nodeForm.passwordClear"),
              }}
            />
            <SecretControl
              title={t("nodeForm.enable")}
              help={t("nodeForm.enableHelp")}
              hasSecret={Boolean(node?.has_enable)}
              mode={enableMode}
              setMode={setEnableMode}
              value={enable}
              setValue={setEnable}
              modeLabels={{
                keep: t("nodeForm.enableKeep"),
                replace: t("nodeForm.enableReplace"),
                clear: t("nodeForm.enableClear"),
              }}
            />
          </div>
          {node?.effective?.password?.set && node.effective.password.source !== "node" ? (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {t("nodeForm.inheritedPassword", {
                source: t(`nodeDetail.sources.${node.effective.password.source}`, {
                  defaultValue: node.effective.password.source,
                }),
              })}
            </p>
          ) : null}
          {node?.effective?.enable?.set && node.effective.enable.source !== "node" ? (
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              {t("nodeForm.inheritedEnable", {
                source: t(`nodeDetail.sources.${node.effective.enable.source}`, {
                  defaultValue: node.effective.enable.source,
                }),
              })}
            </p>
          ) : null}
        </section>

        <section className="space-y-3 border-t pt-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border bg-muted/40 font-mono text-[10px] text-muted-foreground">
              04
            </span>
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("nodeForm.variables")}
            </h3>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.varsHelp")}</p>
          <KeyValueEditor
            value={vars}
            onChange={setVars}
            addLabel={t("nodeForm.addVar")}
            suggestions={variables.map((variable) => variable.name)}
          />
          <KnownVariables variables={variables} />
        </section>

        <section className="space-y-3 border-t pt-6">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md border bg-muted/40 font-mono text-[10px] text-muted-foreground">
              05
            </span>
            <h3 className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              {t("nodeForm.tags")}
            </h3>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">{t("nodeForm.tagsHelp")}</p>
          <KeyValueEditor
            value={tags}
            onChange={setTags}
            addLabel={t("nodeForm.addTag")}
            suggestions={tagKeySuggestions}
            valueSuggestions={tagValueSuggestions}
          />
        </section>

        <details className="group rounded-lg border bg-muted/20">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-medium text-muted-foreground">
            <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
            {t("nodeForm.advancedOptions")}
          </summary>
          <div className="grid gap-4 border-t p-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="node-output">{t("nodeForm.output")}</Label>
              <Input id="node-output" list="node-outputs" {...form.register("output")} />
              <datalist id="node-outputs">
                {outputs.map((output) => (
                  <option key={output} value={output} />
                ))}
              </datalist>
              <p className="text-[11px] text-muted-foreground">{t("nodeForm.outputHelp")}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="node-timeout">{t("nodeForm.timeout")}</Label>
              <Input id="node-timeout" type="number" min={1} max={3600} {...form.register("timeout_seconds", { valueAsNumber: true })} />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="node-prompt">{t("nodeForm.prompt")}</Label>
              <Input id="node-prompt" className="font-mono text-xs" {...form.register("prompt")} />
              <p className="text-[11px] text-muted-foreground">{t("nodeForm.promptHelp")}</p>
            </div>
          </div>
        </details>
      </div>
      <SheetFooter>
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? <Spinner /> : <Save />}
          {submitting ? t("nodeForm.saving") : isEdit ? t("nodeForm.submitEdit") : t("nodeForm.submitCreate")}
        </Button>
      </SheetFooter>
    </form>
  );
}

export function NodeFormSheet({
  open,
  onOpenChange,
  nodeId,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  nodeId?: number | null;
  onSaved?: () => void;
}) {
  const { t } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const nodeQuery = useQuery({
    queryKey: ["node", nodeId],
    queryFn: () => api.node(nodeId as number),
    enabled: open && Boolean(nodeId),
  });
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: api.groups,
    enabled: open && can("groups.write"),
  });
  const catalogQuery = useQuery({
    queryKey: ["config-catalog"],
    queryFn: api.configCatalog,
    enabled: open,
    staleTime: 5 * 60_000,
  });
  const tagsQuery = useQuery({ queryKey: ["node-tags"], queryFn: api.nodeTags, enabled: open });
  const tagCatalog = tagsQuery.data?.items ?? [];
  const tagKeySuggestions = Array.from(
    new Set([...tagCatalog.map((item) => item.key), "Site", "Criticality", "Vendor", "Tier", "Latitude", "Longitude"]),
  ).sort();
  const tagValueSuggestions = tagCatalog.reduce<Record<string, string[]>>((result, item) => {
    result[item.key] = Array.from(new Set([...(result[item.key] ?? []), item.value])).sort();
    return result;
  }, {});

  const node = nodeQuery.data ?? null;

  useEffect(() => {
    if (open) return;
    const frame = requestAnimationFrame(() => {
      document.body.style.pointerEvents = "";
      document.body.style.overflow = "";
    });
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(
    () => () => {
      // Radix/Select can leave the body locked when the sheet unmounts mid-close.
      document.body.style.pointerEvents = "";
      document.body.style.overflow = "";
    },
    [],
  );

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60]">
      <button
        type="button"
        aria-label={t("common.close")}
        className="absolute inset-0 h-full w-full bg-slate-950/40 backdrop-blur-[1px]"
        onClick={() => onOpenChange(false)}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={nodeId ? t("nodeForm.editTitle") : t("nodeForm.createTitle")}
        className="absolute inset-y-0 right-0 flex w-[min(94vw,38rem)] flex-col border-l bg-card shadow-lift"
      >
        <SheetHeader className="border-b px-6 pb-5 pt-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <KeyRound className="h-4 w-4 text-primary" />
            {nodeId ? t("nodeForm.editTitle") : t("nodeForm.createTitle")}
          </h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {nodeId ? t("nodeForm.editDescription") : t("nodeForm.createDescription")}
          </p>
        </SheetHeader>
        {nodeId && nodeQuery.isLoading ? (
          <div className="space-y-4 p-6">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : nodeId && nodeQuery.isError ? (
          <div className="p-6 text-sm text-destructive">{t("common.loadingError")}</div>
        ) : (
          <NodeForm
            key={node?.id ?? "new"}
            node={node}
            groups={groupsQuery.data?.groups ?? []}
            models={catalogQuery.data?.models ?? []}
            modelVendors={catalogQuery.data?.model_vendors ?? {}}
            inputs={catalogQuery.data?.inputs ?? []}
            outputs={catalogQuery.data?.outputs ?? []}
            variables={catalogQuery.data?.vars ?? []}
            tagKeySuggestions={tagKeySuggestions}
            tagValueSuggestions={tagValueSuggestions}
            onCancel={() => onOpenChange(false)}
            onSaved={() => {
              void queryClient.invalidateQueries({ queryKey: ["node", nodeId] });
              onOpenChange(false);
              onSaved?.();
            }}
          />
        )}
      </div>
    </div>
  );
}
