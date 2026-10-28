import { Plus, Trash2, UsersRound } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { AutocompleteInput } from "@/components/shared/autocomplete-input";
import { KeyValueEditor } from "@/components/shared/key-value-editor";
import { PasswordInput } from "@/components/shared/password-input";
import { MapListEditor, type MapEntry } from "@/components/shared/map-list-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type ModelRecord = Record<string, unknown> & {
  username?: string | null;
  password?: string | null;
  enable?: string | null;
  vars?: Record<string, unknown>;
};

export function ConfigModels({
  modelsConfig,
  onChange,
  modelMap,
  onModelMapChange,
  models,
}: {
  modelsConfig: unknown;
  onChange: (value: Record<string, ModelRecord>) => void;
  modelMap: unknown;
  onModelMapChange: (value: MapEntry[]) => void;
  models: string[];
}) {
  const { t } = useTranslation();
  const [newModel, setNewModel] = useState("");
  const entries = (modelsConfig && typeof modelsConfig === "object" && !Array.isArray(modelsConfig)
    ? modelsConfig
    : {}) as Record<string, ModelRecord>;

  const update = (name: string, patch: Partial<ModelRecord>) => {
    onChange({ ...entries, [name]: { ...entries[name], ...patch } });
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold">{t("config.tabs.models")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{t("config.modelsDescription")}</p>
      </div>

      <div className="rounded-lg border bg-card p-4">
        <div className="mb-4 flex flex-wrap items-end gap-2">
          <div className="min-w-[14rem] flex-1 space-y-1">
            <Label>{t("config.addModelOverride")}</Label>
            <AutocompleteInput
              value={newModel}
              suggestions={models}
              onChange={(event) => setNewModel(event.target.value)}
              className="h-8 font-mono text-xs"
              placeholder={t("nodeForm.modelPlaceholder")}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!newModel.trim() || Boolean(entries[newModel.trim()])}
            onClick={() => {
              onChange({ ...entries, [newModel.trim()]: { username: null, password: null, vars: {} } });
              setNewModel("");
            }}
          >
            <Plus />
            {t("common.add")}
          </Button>
        </div>

        {Object.keys(entries).length === 0 ? (
          <p className="rounded-md border border-dashed px-4 py-8 text-center text-xs text-muted-foreground">{t("groups.noModels")}</p>
        ) : (
          <div className="space-y-3">
            {Object.entries(entries).map(([name, record]) => (
              <div key={name} className="rounded-md border bg-muted/10 p-3">
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card text-primary">
                    <UsersRound className="h-3.5 w-3.5" />
                  </span>
                  <span className="font-mono text-xs font-medium">{name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-xs"
                    className="ml-auto text-muted-foreground hover:text-destructive"
                    onClick={() => {
                      const next = { ...entries };
                      delete next[name];
                      onChange(next);
                    }}
                    aria-label={t("common.remove")}
                  >
                    <Trash2 />
                  </Button>
                </div>
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1">
                    <Label>{t("config.username")}</Label>
                    <Input
                      value={typeof record.username === "string" ? record.username : ""}
                      onChange={(event) => update(name, { username: event.target.value || undefined })}
                      className="h-8"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>{t("config.password")}</Label>
                    <PasswordInput
                      value={typeof record.password === "string" ? record.password : ""}
                      onChange={(event) => update(name, { password: event.target.value || undefined })}
                      className="h-8"
                      autoComplete="new-password"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label>{t("config.enable")}</Label>
                    <PasswordInput
                      value={typeof record.enable === "string" ? record.enable : ""}
                      onChange={(event) => update(name, { enable: event.target.value || undefined })}
                      className="h-8"
                      autoComplete="new-password"
                    />
                  </div>
                </div>
                <div className="mt-3 space-y-1">
                  <Label>{t("config.varsTitle")}</Label>
                  <KeyValueEditor
                    value={(record.vars && typeof record.vars === "object" ? record.vars : {}) as Record<string, unknown>}
                    onChange={(vars) => update(name, { vars })}
                    addLabel={t("config.addVar")}
                    className={cn("text-xs")}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <MapListEditor
        value={modelMap}
        onChange={onModelMapChange}
        title={t("config.modelMap")}
        help={t("config.modelMapHelp")}
      />
    </div>
  );
}
