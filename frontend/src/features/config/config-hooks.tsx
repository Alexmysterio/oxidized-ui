import { Plus, Trash2, TriangleAlert, Webhook } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ConfigField } from "@/features/config/config-field";
import { HookNameInput } from "@/features/config/hook-name-input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { CatalogHook } from "@/types/api";

type HookRecord = Record<string, unknown> & { type: string; events: string[] };

export function ConfigHooks({
  value,
  onChange,
  hookTypes,
  models,
}: {
  value: unknown;
  onChange: (value: Record<string, HookRecord>) => void;
  hookTypes: Record<string, CatalogHook>;
  models: string[];
}) {
  const { t } = useTranslation();
  const [counter, setCounter] = useState(1);
  const hooks = (value && typeof value === "object" && !Array.isArray(value) ? value : {}) as Record<string, HookRecord>;
  const names = Object.keys(hooks);
  const hasExec = names.some((name) => hooks[name]?.type === "exec");

  const update = (name: string, next: HookRecord) => {
    onChange({ ...hooks, [name]: next });
  };

  const add = () => {
    let name = `hook_${counter}`;
    while (hooks[name]) {
      setCounter((current) => current + 1);
      name = `hook_${counter + 1}`;
    }
    setCounter((current) => current + 1);
    onChange({ ...hooks, [name]: { type: "exec", events: ["post_store"] } });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">{t("config.tabs.hooks")}</h2>
          <p className="mt-1 text-xs text-muted-foreground">{t("config.hooksDescription")}</p>
        </div>
        <Button variant="outline" size="sm" onClick={add}>
          <Plus />
          {t("config.addHook")}
        </Button>
      </div>
      {hasExec ? (
        <div className="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/[0.045] p-3 text-xs">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          {t("config.execWarning")}
        </div>
      ) : null}
      {names.length === 0 ? (
        <div className="rounded-lg border border-dashed px-5 py-10 text-center text-sm text-muted-foreground">{t("config.noHooks")}</div>
      ) : (
        <div className="space-y-3">
          {names.map((name) => {
            const hook = hooks[name];
            const type = hookTypes[hook.type];
            return (
              <div key={name} className="rounded-lg border bg-card p-4 shadow-xs">
                <div className="mb-4 flex flex-wrap items-end gap-3">
                  <span className="mb-2 flex h-7 w-7 items-center justify-center rounded-md border bg-muted/30 text-muted-foreground">
                    <Webhook className="h-3.5 w-3.5" />
                  </span>
                  <div className="min-w-[10rem] flex-1 space-y-1">
                    <Label>{t("config.hookName")}</Label>
                    <HookNameInput
                      name={name}
                      ariaLabel={t("config.hookName")}
                      onRename={(nextName) => {
                        if (hooks[nextName]) return;
                        const next = { ...hooks };
                        delete next[name];
                        next[nextName] = hook;
                        onChange(next);
                      }}
                    />
                  </div>
                  <div className="min-w-[10rem] flex-1 space-y-1">
                    <Label>{t("config.hookType")}</Label>
                    <Select
                      value={hook.type}
                      onValueChange={(nextType) => {
                        const next: HookRecord = { type: nextType, events: Array.isArray(hook.events) ? hook.events : [] };
                        update(name, next);
                      }}
                    >
                      <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(hookTypes).map(([typeId, descriptor]) => (
                          <SelectItem key={typeId} value={typeId}>
                            {t(descriptor.label_code, { defaultValue: typeId })}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => {
                      const next = { ...hooks };
                      delete next[name];
                      onChange(next);
                    }}
                    aria-label={t("common.remove")}
                  >
                    <Trash2 />
                  </Button>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2 sm:col-span-2">
                    <Label>{t("config.hookEvents")}</Label>
                    <div className="flex flex-wrap gap-1.5">
                      {(type?.events ?? []).map((event) => {
                        const events = Array.isArray(hook.events) ? hook.events : [];
                        const active = events.includes(event);
                        return (
                          <button
                            key={event}
                            type="button"
                            aria-pressed={active}
                            onClick={() => {
                              const nextEvents = active
                                ? events.filter((item) => item !== event)
                                : [...events, event];
                              update(name, { ...hook, events: nextEvents });
                            }}
                            className={cn(
                              "rounded-md border px-2 py-1 font-mono text-[10px] transition-colors",
                              active
                                ? "border-primary/35 bg-primary/[0.07] text-primary"
                                : "border-border bg-card text-muted-foreground hover:border-foreground/20",
                            )}
                          >
                            {t(`oxidized.events.${event}`, { defaultValue: event })}
                          </button>
                        );
                      })}
                      {type?.suggested_events?.length ? (
                        <Badge variant="outline" className="ml-1 normal-case tracking-normal">
                          {t("config.hookEvents")}: {type.suggested_events.length}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  {(type?.fields ?? []).map((field) => (
                    <ConfigField
                      key={field.path}
                      field={field}
                      value={hook[field.path]}
                      onChange={(nextValue) => {
                        const next = { ...hook };
                        if (nextValue === undefined) delete next[field.path];
                        else next[field.path] = nextValue;
                        update(name, next);
                      }}
                      models={models}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
