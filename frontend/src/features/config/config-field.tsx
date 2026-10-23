import { LockKeyhole } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { KeyValueEditor } from "@/components/shared/key-value-editor";
import { MapListEditor } from "@/components/shared/map-list-editor";
import { PasswordInput } from "@/components/shared/password-input";
import { Badge } from "@/components/ui/badge";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { CatalogField } from "@/types/api";

function JsonField({ value, onChange, disabled, id }: { value: unknown; onChange: (value: unknown) => void; disabled?: boolean; id?: string }) {
  const { t } = useTranslation();
  const [text, setText] = useState(() => JSON.stringify(value ?? [], null, 2));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    setText(JSON.stringify(value ?? [], null, 2));
    setInvalid(false);
  }, [value]);
  return (
    <div className="space-y-1">
      <Textarea
        id={id}
        value={text}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value;
          setText(next);
          try {
            onChange(next.trim() ? JSON.parse(next) : undefined);
            setInvalid(false);
          } catch {
            setInvalid(true);
          }
        }}
        className={cn("min-h-24 font-mono text-xs", invalid && "border-destructive")}
      />
      {invalid ? <p className="text-[10px] text-destructive">{t("config.jsonInvalid")}</p> : null}
    </div>
  );
}

function ListField({ value, onChange, disabled, id }: { value: unknown; onChange: (value: unknown) => void; disabled?: boolean; id?: string }) {
  const initial = Array.isArray(value) ? value.join(", ") : value == null ? "" : String(value);
  const [text, setText] = useState(initial);
  useEffect(() => setText(initial), [initial]);
  return (
    <Input
      id={id}
      value={text}
      disabled={disabled}
      onChange={(event) => {
        const next = event.target.value;
        setText(next);
        onChange(
          next
            .split(",")
            .map((part) => part.trim())
            .filter(Boolean),
        );
      }}
      className="font-mono text-xs"
    />
  );
}

function MultiSelectField({
  options,
  value,
  onChange,
  path,
  disabled,
}: {
  options: string[];
  value: unknown;
  onChange: (value: unknown) => void;
  path: string;
  disabled?: boolean;
}) {
  const selected = Array.isArray(value)
    ? value.map(String)
    : typeof value === "string"
      ? value.split(",").map((part) => part.trim()).filter(Boolean)
      : [];
  const toggle = (option: string) => {
    const next = selected.includes(option) ? selected.filter((item) => item !== option) : [...selected, option];
    onChange(path === "input.default" ? next.join(", ") : next);
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((option) => {
        const active = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            disabled={disabled}
            onClick={() => toggle(option)}
            aria-pressed={active}
            className={cn(
              "rounded-md border px-2 py-1 font-mono text-[10px] transition-colors disabled:opacity-50",
              active
                ? "border-primary/35 bg-primary/[0.07] text-primary"
                : "border-border bg-card text-muted-foreground hover:border-foreground/20",
            )}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}

export function ConfigField({
  field,
  value,
  onChange,
  disabled = false,
  models = [],
}: {
  field: CatalogField;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
  models?: string[];
}) {
  const { t } = useTranslation();
  const label = t(field.label_code, { defaultValue: field.path });
  const help = t(field.help_code, { defaultValue: "" });
  const options =
    field.options === "__models__"
      ? []
      : Array.isArray(field.options)
        ? field.options.map(String)
        : [];
  const lock = disabled || field.managed;
  const fieldId = `config-${field.path.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const hasLabelTarget = !lock && !["boolean", "keyvalue", "map_list", "multiselect"].includes(field.type);

  let control: React.ReactNode;
  if (lock) {
    const display =
      field.sensitive && value
        ? "••••••••"
        : typeof value === "object" && value !== null
          ? JSON.stringify(value)
          : value === undefined || value === null || value === ""
            ? "—"
            : String(value);
    control = (
      <div className="flex h-9 items-center gap-2 rounded-md border border-dashed bg-muted/20 px-3">
        <LockKeyhole className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate font-mono text-[11px] text-muted-foreground">{display}</span>
        <Badge variant="outline" className="ml-auto shrink-0">{t("config.managed")}</Badge>
      </div>
    );
  } else if (field.type === "boolean") {
    control = (
      <div className="flex h-9 items-center gap-3 rounded-md border bg-card px-3">
        <Switch checked={Boolean(value)} onCheckedChange={onChange} aria-label={label} />
        <span className="text-xs text-muted-foreground">{value ? t("common.enabled") : t("common.disabled")}</span>
      </div>
    );
  } else if (field.type === "integer") {
    control = (
      <Input
        id={fieldId}
        type="number"
        min={field.min}
        max={field.max}
        value={typeof value === "number" ? value : value === undefined || value === null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value === "" ? undefined : Number(event.target.value))}
        className="font-mono text-xs"
      />
    );
  } else if (field.type === "select") {
    const selectOptions = field.options === "__models__" ? models : options;
    control = (
      <Select
        value={value === undefined || value === null || value === "" ? "__unset__" : String(value)}
        onValueChange={(next) => onChange(next === "__unset__" ? undefined : next)}
      >
        <SelectTrigger id={fieldId} className="font-mono text-xs"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="__unset__">{t("common.default")}</SelectItem>
          {selectOptions.map((option) => (
            <SelectItem key={option} value={option} className="font-mono text-xs">{option}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  } else if (field.type === "multiselect") {
    control = (
      <MultiSelectField
        path={field.path}
        options={options}
        value={value}
        onChange={onChange}
        disabled={lock}
      />
    );
  } else if (field.type === "keyvalue") {
    control = (
      <KeyValueEditor
        value={(value && typeof value === "object" && !Array.isArray(value) ? value : {}) as Record<string, unknown>}
        onChange={onChange}
        addLabel={t("config.addVar")}
      />
    );
  } else if (field.type === "map_list") {
    control = <MapListEditor value={value} onChange={onChange} title={field.path} help={help} />;
  } else if (field.type === "json") {
    control = <JsonField id={fieldId} value={value} onChange={onChange} disabled={lock} />;
  } else if (field.type === "list") {
    control = <ListField id={fieldId} value={value} onChange={onChange} disabled={lock} />;
  } else if (field.type === "secret") {
    control = (
      <PasswordInput
        id={fieldId}
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || undefined)}
        autoComplete="new-password"
      />
    );
  } else {
    control = (
      <Input
        id={fieldId}
        value={typeof value === "string" ? value : value === undefined || value === null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value || undefined)}
        className={field.type === "regex" ? "font-mono text-xs" : undefined}
      />
    );
  }

  if (field.type === "map_list") {
    return (
      <div className="sm:col-span-2">
        {control}
      </div>
    );
  }

  const showDefault =
    field.default !== undefined &&
    field.default !== null &&
    (value === undefined || value === null || value === "") &&
    !["boolean", "keyvalue", "map_list", "json"].includes(field.type);

  return (
    <div className={cn("space-y-2", field.type === "keyvalue" && "sm:col-span-2")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Label htmlFor={hasLabelTarget ? fieldId : undefined}>{label}</Label>
        <span className="font-mono text-[9px] text-muted-foreground/65">{field.path}</span>
        {field.deprecated ? <Badge variant="warning">{t("config.deprecated")}</Badge> : null}
        {field.sensitive ? <Badge variant="outline">{t("config.sensitive")}</Badge> : null}
      </div>
      {control}
      {help ? <p className="text-[11px] leading-relaxed text-muted-foreground">{help}</p> : null}
      {showDefault ? (
        <p className="font-mono text-[9px] text-muted-foreground/60">
          {t("config.defaultValue", { value: typeof field.default === "object" ? JSON.stringify(field.default) : String(field.default) })}
        </p>
      ) : null}
    </div>
  );
}
