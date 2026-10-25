import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  Clock3,
  Code2,
  Download,
  FileCode2,
  GitBranch,
  History,
  Save,
  ShieldCheck,
  Sparkles,
  UploadCloud,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { CodeEditor } from "@/components/shared/code-editor";
import { KnownVariables } from "@/components/shared/known-variables";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { CopyButton } from "@/components/shared/copy-button";
import { DiffView } from "@/components/shared/diff-view";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { PageSkeleton, Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfigField } from "@/features/config/config-field";
import { ConfigHooks } from "@/features/config/config-hooks";
import { ConfigModels } from "@/features/config/config-models";
import { ConfigRevisionsSheet } from "@/features/config/config-revisions";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, notifyError } from "@/lib/errors";
import { getPath, setPath } from "@/lib/utils";
import type { Catalog, ConfigState, ConfigValidation, Job } from "@/types/api";
import type { MapEntry } from "@/components/shared/map-list-editor";

type TabId = "general" | "input" | "output" | "source" | "hooks" | "models" | "rest" | "advanced";
type Action = "save" | "apply";

const tabs: TabId[] = ["general", "input", "output", "source", "hooks", "models", "rest", "advanced"];

function sectionDescriptionKey(tab: TabId): string {
  return `config.${tab}Description`;
}

function FieldGrid({
  fields,
  config,
  setValue,
  models,
}: {
  fields: Catalog["fields"];
  config: Record<string, unknown>;
  setValue: (path: string, value: unknown) => void;
  models: string[];
}) {
  return (
    <div className="grid gap-x-5 gap-y-5 sm:grid-cols-2">
      {fields.map((field) => (
        <ConfigField
          key={field.path}
          field={field}
          value={getPath(config, field.path)}
          onChange={(value) => setValue(field.path, value)}
          models={models}
        />
      ))}
    </div>
  );
}

function ApplyJobPanel({
  job,
  onDismiss,
  onRetry,
}: {
  job: Job;
  onDismiss: () => void;
  onRetry: () => void;
}) {
  const { t } = useTranslation();
  const total = Math.max(1, job.progress.total);
  const percent = job.status === "succeeded" ? 100 : Math.round((job.progress.done / total) * 100);
  const failed = job.status === "failed";
  return (
    <div className={`flex flex-col gap-2 rounded-lg border p-3 text-xs sm:flex-row sm:items-center ${failed ? "border-destructive/25 bg-destructive/[0.04]" : "border-primary/20 bg-primary/[0.04]"}`}>
      {failed ? <AlertTriangle className="h-4 w-4 shrink-0 text-destructive" /> : <Spinner className="text-primary" />}
      <div className="min-w-0 flex-1">
        <p className={failed ? "font-medium text-destructive" : "font-medium text-primary"}>
          {failed ? t("config.applyFailed") : job.status === "running" || job.status === "queued" ? t("config.restarting") : t("config.appliedToast")}
        </p>
        {job.error ? <p className="mt-0.5 text-[11px] text-muted-foreground">{t(`errors.${job.error.code}`, { defaultValue: job.error.code })}</p> : null}
      </div>
      {!failed ? (
        <div className="flex items-center gap-2">
          <div className="h-1 w-36 overflow-hidden rounded-full bg-primary/15">
            <div className="h-full rounded-full bg-primary transition-[width]" style={{ width: `${percent}%` }} />
          </div>
          <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{percent}%</span>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button variant="outline" size="xs" onClick={onRetry}>{t("common.retry")}</Button>
          <Button variant="ghost" size="xs" onClick={onDismiss}>{t("common.close")}</Button>
        </div>
      )}
    </div>
  );
}

export function ConfigPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<TabId>("general");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [yamlText, setYamlText] = useState("");
  const [baseConfig, setBaseConfig] = useState<Record<string, unknown>>({});
  const [baseYaml, setBaseYaml] = useState("");
  const [signature, setSignature] = useState("");
  const [preview, setPreview] = useState<ConfigValidation | null>(null);
  const [pendingAction, setPendingAction] = useState<Action | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [applyExistingOpen, setApplyExistingOpen] = useState(false);
  const [jobId, setJobId] = useState<number | null>(null);
  const [applyRevisionId, setApplyRevisionId] = useState<number | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const [yamlValidating, setYamlValidating] = useState(false);
  const notifiedJob = useRef<number | null>(null);
  usePageTitle("config.title");

  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.config });
  const catalogQuery = useQuery({ queryKey: ["config-catalog"], queryFn: api.configCatalog, staleTime: 5 * 60_000 });

  useEffect(() => {
    const data: ConfigState | undefined = configQuery.data;
    if (!data) return;
    const nextSignature = `${data.applied?.id ?? 0}:${data.draft?.id ?? 0}`;
    if (nextSignature === signature) return;
    setSignature(nextSignature);
    setConfig(data.config);
    setBaseConfig(data.config);
    setYamlText(data.editable_yaml);
    setBaseYaml(data.editable_yaml);
  }, [configQuery.data, signature]);

  const formDirty = useMemo(() => JSON.stringify(config) !== JSON.stringify(baseConfig), [config, baseConfig]);
  const yamlDirty = yamlText !== baseYaml;
  const dirty = tab === "advanced" ? yamlDirty : formDirty;
  const catalog = catalogQuery.data;
  const fields = catalog?.fields ?? [];
  const generalFields = fields.filter((field) => field.section === "general" && !["vars", "group_map", "model_map"].includes(field.path));
  const generalBasic = generalFields.filter((field) => field.level !== "advanced");
  const generalAdvanced = generalFields.filter((field) => field.level === "advanced");
  const varsField = fields.find((field) => field.path === "vars");
  const groupMapField = fields.find((field) => field.path === "group_map");
  const inputFields = fields.filter((field) => field.section === "input");
  const sourceFields = fields.filter((field) => field.section === "source");
  const restFields = fields.filter((field) => field.section === "rest");
  const outputDefault = String(getPath(config, "output.default") ?? "file");
  const outputFields = fields.filter(
    (field) =>
      field.section === "output" &&
      (field.path === "output.default" ||
        field.path === "output.clean_obsolete_nodes" ||
        field.path.startsWith(`output.${outputDefault}.`)),
  );
  const sourceReadTimeout = sourceFields.find((field) => field.path === "source.http.read_timeout");

  const setValue = (path: string, value: unknown) => {
    setConfig((current) => setPath(current, path, value));
  };

  const validation = useMutation({
    mutationFn: (action: Action) => {
      setPendingAction(action);
      return api.validateConfig(tab === "advanced" ? { yaml: yamlText } : { config });
    },
    onSuccess: (data) => {
      setPreview(data);
      setPreviewOpen(true);
    },
    onError: (error) => {
      setPendingAction(null);
      notifyError(t, error);
    },
  });

  const jobQuery = useQuery({
    queryKey: ["config-apply-job", jobId],
    queryFn: () => api.job(jobId as number),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === "succeeded" || data.status === "failed" || data.status === "cancelled") return false;
      return 1500;
    },
  });

  useEffect(() => {
    const job = jobQuery.data;
    if (!job || notifiedJob.current === job.id) return;
    if (job.status === "succeeded") {
      notifiedJob.current = job.id;
      toast.success(t("config.appliedToast"));
      void queryClient.invalidateQueries({ queryKey: ["config"] });
      void queryClient.invalidateQueries({ queryKey: ["config-revisions"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setJobId(null);
      setApplyRevisionId(null);
      setApplyError(null);
    } else if (job.status === "failed" || job.status === "cancelled") {
      notifiedJob.current = job.id;
      setApplyError(job.error ? t(`errors.${job.error.code}`, { defaultValue: job.error.code }) : t("config.applyFailed"));
      void queryClient.invalidateQueries({ queryKey: ["config"] });
    }
  }, [jobQuery.data, queryClient, t]);

  const commitSave = async (action: Action) => {
    if (!preview || !configQuery.data) return;
    setPreviewOpen(false);
    setApplyError(null);
    try {
      const noChanges = preview.diff.stats.additions === 0 && preview.diff.stats.deletions === 0;
      let revisionId = configQuery.data.draft?.id ?? null;
      if (!noChanges) {
        const draft = await api.saveConfigDraft({
          ...(tab === "advanced" ? { yaml: yamlText } : { config: preview.config }),
          expected_revision_id: configQuery.data.draft?.id ?? configQuery.data.applied?.id ?? null,
          origin: tab === "advanced" ? "yaml" : "form",
        });
        revisionId = draft.revision.id;
      }
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      await queryClient.invalidateQueries({ queryKey: ["config-revisions"] });
      toast.success(t("config.savedToast"));
      if (action === "apply") {
        if (!revisionId) {
          toast.error(t("config.noDraft"));
          return;
        }
        const job = await api.applyConfig(revisionId);
        setApplyRevisionId(revisionId);
        setJobId(job.id);
        notifiedJob.current = null;
      }
    } catch (error) {
      notifyError(t, error);
    } finally {
      setPendingAction(null);
      setPreview(null);
    }
  };

  const schedulesQuery = useQuery({
    queryKey: ["config-schedules"],
    queryFn: api.configSchedules,
    enabled: scheduleOpen,
  });

  const createSchedule = useMutation({
    mutationFn: () => api.scheduleConfig(configQuery.data?.draft?.id as number, new Date(scheduleAt).toISOString()),
    onSuccess: () => {
      setScheduleOpen(false);
      setScheduleAt("");
      setScheduleError(null);
      toast.success(t("config.scheduleCreated"));
      void queryClient.invalidateQueries({ queryKey: ["config-schedules"] });
    },
    onError: (error) => setScheduleError(errorMessage(t, error)),
  });

  const cancelSchedule = useMutation({
    mutationFn: (id: number) => api.cancelConfigSchedule(id),
    onSuccess: () => {
      toast.success(t("config.scheduleCancelled"));
      void queryClient.invalidateQueries({ queryKey: ["config-schedules"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const applyDraft = async () => {
    if (!configQuery.data?.draft) return;
    setApplyExistingOpen(false);
    setApplyError(null);
    try {
      const job = await api.applyConfig(configQuery.data.draft.id);
      setApplyRevisionId(configQuery.data.draft.id);
      setJobId(job.id);
      notifiedJob.current = null;
    } catch (error) {
      notifyError(t, error);
    }
  };

  const validateYamlNow = async (switchToForm = false): Promise<boolean> => {
    setYamlValidating(true);
    try {
      const data = await api.validateConfig({ yaml: yamlText });
      setConfig(data.config);
      setBaseConfig(data.config);
      setYamlText(data.editable_yaml);
      setBaseYaml(data.editable_yaml);
      toast.success(t("config.yamlValid"));
      if (switchToForm) setTab("general");
      return true;
    } catch (error) {
      notifyError(t, error);
      return false;
    } finally {
      setYamlValidating(false);
    }
  };

  const changeTab = async (next: string) => {
    if (next === tab) return;
    if (switching) return;
    setSwitching(true);
    try {
      if (next === "advanced" && formDirty) {
        const data = await api.validateConfig({ config });
        setConfig(data.config);
        setBaseConfig(data.config);
        setYamlText(data.editable_yaml);
        setBaseYaml(data.editable_yaml);
      } else if (tab === "advanced" && yamlDirty) {
        const data = await api.validateConfig({ yaml: yamlText });
        setConfig(data.config);
        setBaseConfig(data.config);
        setYamlText(data.editable_yaml);
        setBaseYaml(data.editable_yaml);
      }
      setTab(next as TabId);
    } catch (error) {
      notifyError(t, error);
    } finally {
      setSwitching(false);
    }
  };

  if (configQuery.isLoading || catalogQuery.isLoading) return <PageSkeleton />;
  if (configQuery.isError || catalogQuery.isError || !configQuery.data || !catalog) {
    return <ErrorState onRetry={() => { void configQuery.refetch(); void catalogQuery.refetch(); }} />;
  }

  const data = configQuery.data;
  const revisionLabel = data.draft ? `#${data.draft.id}` : data.applied ? `#${data.applied.id}` : "—";
  const noChanges = preview ? preview.diff.stats.additions === 0 && preview.diff.stats.deletions === 0 : false;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <FileCode2 className="h-3.5 w-3.5 text-primary" />
            {t("nav.operations")}
          </>
        }
        title={t("config.title")}
        description={t("config.subtitle")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => setHistoryOpen(true)}>
              <History />
              {t("config.showHistory")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => validation.mutate("save")} disabled={validation.isPending || !can("config.write")}>
              {validation.isPending && pendingAction === "save" ? <Spinner /> : <Save />}
              {t("config.saveDraft")}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setScheduleOpen(true)} disabled={!configQuery.data?.draft}>
              <Clock3 />
              {t("config.schedule")}
            </Button>
            <Button size="sm" onClick={() => validation.mutate("apply")} disabled={validation.isPending || !can("config.apply")} title={t("config.saveApplyHint")}>
              {validation.isPending && pendingAction === "apply" ? <Spinner /> : <UploadCloud />}
              {t("config.saveApply")}
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="success" className="normal-case tracking-normal">
          <Check className="h-3 w-3" />
          {t("config.applied")} {data.applied ? `#${data.applied.id}` : "—"}
        </Badge>
        {data.draft ? (
          <Badge variant="warning" className="normal-case tracking-normal">
            <GitBranch className="h-3 w-3" />
            {t("config.draft")} #{data.draft.id}
          </Badge>
        ) : (
          <Badge variant="outline" className="normal-case tracking-normal">{t("config.noDraft")}</Badge>
        )}
        {dirty ? <Badge variant="info" className="normal-case tracking-normal">{t("config.unsavedChanges")}</Badge> : null}
        {data.drift.detected ? <Badge variant="destructive" className="normal-case tracking-normal">{t("config.driftTitle")}</Badge> : null}
        <span className="ml-auto hidden font-mono text-[9px] text-muted-foreground sm:block">{revisionLabel}</span>
      </div>

      {data.drift.detected ? (
        <div className="flex gap-3 rounded-lg border border-destructive/25 bg-destructive/[0.045] p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div>
            <p className="text-xs font-medium text-destructive">{t("config.driftTitle")}</p>
            <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{t("config.driftDescription")}</p>
          </div>
        </div>
      ) : null}

      {data.draft ? (
        <div className="flex flex-col gap-3 rounded-lg border border-primary/20 bg-primary/[0.035] p-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <GitBranch className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
            <div>
              <p className="text-xs font-medium text-primary">{t("config.draftBanner")}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{t("config.draftBannerDescription")}</p>
            </div>
          </div>
          <Button size="sm" variant="outline" onClick={() => setApplyExistingOpen(true)} disabled={dirty}>
            <UploadCloud />
            {t("config.applyDraft")}
          </Button>
        </div>
      ) : null}

      {jobQuery.data && (jobQuery.data.status === "queued" || jobQuery.data.status === "running" || applyError) ? (
        <ApplyJobPanel
          job={jobQuery.data}
          onDismiss={() => { setJobId(null); setApplyError(null); }}
          onRetry={() => {
            if (!applyRevisionId) return;
            setApplyError(null);
            void api.applyConfig(applyRevisionId).then((job) => {
              setJobId(job.id);
              notifiedJob.current = null;
            }).catch((error) => notifyError(t, error));
          }}
        />
      ) : null}
      {applyError && !jobQuery.data ? (
        <div className="rounded-lg border border-destructive/25 bg-destructive/[0.04] p-3 text-xs text-destructive">{applyError}</div>
      ) : null}

      <Card>
        <CardContent className="p-4 sm:p-5">
          <Tabs value={tab} onValueChange={(value) => void changeTab(value)}>
            <div className="flex items-center gap-2 overflow-x-auto">
              <TabsList className="h-auto min-w-max justify-start bg-muted/70">
                {tabs.map((item) => (
                  <TabsTrigger key={item} value={item} className="whitespace-nowrap text-xs">
                    {t(`config.tabs.${item}`)}
                  </TabsTrigger>
                ))}
              </TabsList>
              {switching ? <Spinner className="text-muted-foreground" /> : null}
            </div>

            <div className="mt-5 border-t pt-5">
              <div className="mb-5 flex flex-col gap-1">
                <h2 className="text-sm font-semibold">{t(`config.tabs.${tab}`)}</h2>
                <p className="text-xs text-muted-foreground">{t(sectionDescriptionKey(tab))}</p>
              </div>

              <TabsContent value="general" className="mt-0 space-y-7">
                <FieldGrid fields={generalBasic} config={config} setValue={setValue} models={catalog.models} />
                {varsField ? (
                  <div className="rounded-lg border bg-muted/10 p-4">
                    <div className="mb-3">
                      <h3 className="text-xs font-semibold">{t("config.varsTitle")}</h3>
                      <p className="mt-1 text-[11px] text-muted-foreground">{t("config.varsDescription")}</p>
                    </div>
                    <ConfigField
                      field={varsField}
                      value={getPath(config, "vars")}
                      onChange={(value) => setValue("vars", value)}
                      models={catalog.models}
                    />
                    <div className="mt-3">
                      <KnownVariables variables={catalog.vars} />
                    </div>
                  </div>
                ) : null}
                {groupMapField ? (
                  <div className="rounded-lg border bg-muted/10 p-4">
                    <ConfigField
                      field={groupMapField}
                      value={getPath(config, "group_map")}
                      onChange={(value) => setValue("group_map", value)}
                      models={catalog.models}
                    />
                  </div>
                ) : null}
                {generalAdvanced.length ? (
                  <details className="rounded-lg border bg-muted/10">
                    <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-xs font-medium text-muted-foreground">
                      <Code2 className="h-3.5 w-3.5" />
                      {t("config.advancedFields")}
                    </summary>
                    <div className="border-t p-4">
                      <FieldGrid fields={generalAdvanced} config={config} setValue={setValue} models={catalog.models} />
                    </div>
                  </details>
                ) : null}
              </TabsContent>

              <TabsContent value="input" className="mt-0">
                <FieldGrid fields={inputFields} config={config} setValue={setValue} models={catalog.models} />
              </TabsContent>

              <TabsContent value="output" className="mt-0 space-y-5">
                <div className="flex flex-wrap items-center gap-2 rounded-md border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  {t("config.outputDescription")}
                </div>
                <FieldGrid fields={outputFields} config={config} setValue={setValue} models={catalog.models} />
              </TabsContent>

              <TabsContent value="source" className="mt-0 space-y-5">
                {sourceReadTimeout ? (
                  <div className="max-w-sm">
                    <ConfigField
                      field={sourceReadTimeout}
                      value={getPath(config, sourceReadTimeout.path)}
                      onChange={(value) => setValue(sourceReadTimeout.path, value)}
                      models={catalog.models}
                    />
                  </div>
                ) : null}
              </TabsContent>

              <TabsContent value="hooks" className="mt-0">
                <ConfigHooks
                  value={config.hooks}
                  onChange={(value) => setConfig((current) => ({ ...current, hooks: value }))}
                  hookTypes={catalog.hook_types}
                  models={catalog.models}
                />
              </TabsContent>

              <TabsContent value="models" className="mt-0">
                <ConfigModels
                  modelsConfig={config.models}
                  onChange={(value) => setConfig((current) => ({ ...current, models: value }))}
                  modelMap={config.model_map}
                  onModelMapChange={(value: MapEntry[]) => setValue("model_map", value)}
                  models={catalog.models}
                />
              </TabsContent>

              <TabsContent value="rest" className="mt-0 space-y-5">
                <FieldGrid fields={restFields} config={config} setValue={setValue} models={catalog.models} />
              </TabsContent>

              <TabsContent value="advanced" className="mt-0 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="text-xs font-semibold">{t("config.yamlEditorTitle")}</h3>
                    <p className="mt-1 max-w-2xl text-[11px] text-muted-foreground">{t("config.yamlEditorDescription")}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <CopyButton value={yamlText} label={t("config.copyYaml")} />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const blob = new Blob([yamlText], { type: "text/yaml" });
                        const href = URL.createObjectURL(blob);
                        const anchor = document.createElement("a");
                        anchor.href = href;
                        anchor.download = "oxidized-config.yml";
                        anchor.click();
                        URL.revokeObjectURL(href);
                      }}
                    >
                      <Download />
                      {t("config.downloadYaml")}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => void validateYamlNow()} disabled={yamlValidating}>
                      {yamlValidating ? <Spinner /> : <ShieldCheck />}
                      {t("config.validate")}
                    </Button>
                  </div>
                </div>
                <CodeEditor value={yamlText} onChange={setYamlText} language="yaml" minHeight={480} maxHeight={720} ariaLabel={t("config.yamlEditorTitle")} />
                {yamlDirty ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-warning">
                    <Clock3 className="h-3.5 w-3.5" />
                    {t("config.yamlDirty")}
                    <Button variant="ghost" size="xs" onClick={() => void validateYamlNow(true)} disabled={yamlValidating}>
                      {t("config.reloadToForm")}
                    </Button>
                  </div>
                ) : null}
              </TabsContent>
            </div>
          </Tabs>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed bg-card/50 px-3 py-2 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <GitBranch className="h-3.5 w-3.5" />
          {t("config.configDate")}
        </span>
        <span className="font-mono">{intl.dateTime(data.applied?.applied_at ?? data.draft?.created_at)}</span>
      </div>

      <ConfigRevisionsSheet
        open={historyOpen}
        onOpenChange={setHistoryOpen}
        appliedId={data.applied?.id ?? null}
        draftId={data.draft?.id ?? null}
      />

      <Dialog open={previewOpen} onOpenChange={(open) => { setPreviewOpen(open); if (!open) { setPreview(null); setPendingAction(null); } }}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle>{t("config.previewTitle")}</DialogTitle>
            <DialogDescription>{t("config.previewDescription")}</DialogDescription>
          </DialogHeader>
          {preview ? (
            noChanges ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-lg border border-muted bg-muted/20 p-4 text-sm text-muted-foreground">
                  <Check className="h-4 w-4 text-success" />
                  {t("config.noChanges")}
                </div>
                {pendingAction === "apply" && data.draft ? (
                  <div className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                    <div>
                      <p className="font-medium text-warning">{t("config.confirmApplyTitle")}</p>
                      <p className="mt-0.5 text-muted-foreground">{t("config.confirmApplyDescription")}</p>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <>
                <DiffView diff={preview.diff} fromLabel={t("config.applied")} toLabel={t("config.previewTitle")} />
                {pendingAction === "apply" ? (
                  <div className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                    <div>
                      <p className="font-medium text-warning">{t("config.confirmApplyTitle")}</p>
                      <p className="mt-0.5 text-muted-foreground">{t("config.confirmApplyDescription")}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/[0.035] p-3 text-xs">
                    <Save className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div>
                      <p className="font-medium text-primary">{t("config.confirmSaveTitle")}</p>
                      <p className="mt-0.5 text-muted-foreground">{t("config.confirmSaveDescription")}</p>
                    </div>
                  </div>
                )}
              </>
            )
          ) : (
            <div className="h-56 animate-pulse rounded-lg bg-muted" />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() => pendingAction && void commitSave(pendingAction)}
              disabled={(noChanges && !(pendingAction === "apply" && data.draft)) || !pendingAction}
            >
              {pendingAction === "apply" ? <UploadCloud /> : <Save />}
              {pendingAction === "apply" ? t("config.saveApply") : t("config.saveDraft")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={scheduleOpen} onOpenChange={(open) => { setScheduleOpen(open); if (!open) { setScheduleAt(""); setScheduleError(null); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("config.scheduleTitle")}</DialogTitle>
            <DialogDescription>{t("config.scheduleDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="schedule-at">{t("config.scheduleAt")}</Label>
            <Input id="schedule-at" type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
            {scheduleError ? <p className="text-xs text-destructive">{scheduleError}</p> : null}
          </div>
          <div className="space-y-2">
            {(schedulesQuery.data?.items ?? []).filter((item) => item.status === "pending" || item.status === "running").map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-xs">
                <span className="font-mono">{item.run_at ? intl.dateTime(item.run_at) : "—"} · {item.status}</span>
                <Button type="button" variant="ghost" size="sm" onClick={() => cancelSchedule.mutate(item.id)}>{t("common.cancel")}</Button>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setScheduleOpen(false)}>{t("common.cancel")}</Button>
            <Button type="button" disabled={!scheduleAt || !configQuery.data?.draft || createSchedule.isPending} onClick={() => createSchedule.mutate()}>
              {createSchedule.isPending ? <Spinner /> : <Clock3 />}
              {t("config.scheduleConfirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={applyExistingOpen}
        onOpenChange={setApplyExistingOpen}
        title={t("config.confirmApplyTitle")}
        description={t("config.confirmApplyDescription")}
        confirmLabel={t("config.applyDraft")}
        destructive={false}
        onConfirm={() => void applyDraft()}
      />
    </div>
  );
}
