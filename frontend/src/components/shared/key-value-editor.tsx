import { Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AutocompleteInput } from "@/components/shared/autocomplete-input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface Entry {
  id: number;
  key: string;
  value: string;
}

function toRows(value: Record<string, unknown>): Entry[] {
  return Object.entries(value).map(([key, item], index) => ({
    id: index,
    key,
    value: typeof item === "string" ? item : JSON.stringify(item),
  }));
}

function materialize(rows: Entry[]): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  rows.forEach((row) => {
    if (!row.key.trim()) return;
    const raw = row.value;
    if (raw === "true") result[row.key] = true;
    else if (raw === "false") result[row.key] = false;
    else if (raw === "null") result[row.key] = null;
    else if (raw !== "" && !Number.isNaN(Number(raw)) && String(Number(raw)) === raw) result[row.key] = Number(raw);
    else if ((raw.startsWith("{") && raw.endsWith("}")) || (raw.startsWith("[") && raw.endsWith("]"))) {
      try {
        result[row.key] = JSON.parse(raw);
      } catch {
        result[row.key] = raw;
      }
    } else {
      result[row.key] = raw;
    }
  });
  return result;
}

export function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder,
  valuePlaceholder,
  addLabel,
  className,
  suggestions,
  valueSuggestions,
}: {
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  className?: string;
  suggestions?: string[];
  valueSuggestions?: Record<string, string[]>;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Entry[]>(() => toRows(value));
  const counter = useRef(rows.length);
  const lastSerialized = useRef(JSON.stringify(materialize(rows)));

  useEffect(() => {
    const incoming = JSON.stringify(value);
    if (incoming !== lastSerialized.current) {
      const next = toRows(value);
      counter.current = Math.max(counter.current, next.length);
      setRows(next);
      lastSerialized.current = incoming;
    }
  }, [value]);

  const commit = (next: Entry[]) => {
    setRows(next);
    const materialized = materialize(next);
    lastSerialized.current = JSON.stringify(materialized);
    onChange(materialized);
  };

  return (
    <div className={cn("space-y-2", className)}>
      {rows.length > 0 ? (
        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.id} className="flex items-start gap-2">
              <div className="grid flex-1 grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)] gap-2">
                <AutocompleteInput
                  value={row.key}
                  suggestions={suggestions ?? []}
                  placeholder={keyPlaceholder ?? t("nodeForm.variableKey")}
                  aria-label={keyPlaceholder ?? t("nodeForm.variableKey")}
                  onChange={(event) => {
                    const next = rows.map((item) => (item.id === row.id ? { ...item, key: event.target.value } : item));
                    commit(next);
                  }}
                  className="font-mono text-xs"
                />
                <AutocompleteInput
                  value={row.value}
                  suggestions={valueSuggestions?.[row.key] ?? []}
                  placeholder={valuePlaceholder ?? t("nodeForm.variableValue")}
                  aria-label={valuePlaceholder ?? t("nodeForm.variableValue")}
                  onChange={(event) => {
                    const next = rows.map((item) => (item.id === row.id ? { ...item, value: event.target.value } : item));
                    commit(next);
                  }}
                  className="font-mono text-xs"
                />
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="mt-0.5 text-muted-foreground hover:text-destructive"
                onClick={() => commit(rows.filter((item) => item.id !== row.id))}
                aria-label={t("common.remove")}
                title={t("common.remove")}
              >
                <X />
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <p className="rounded-md border border-dashed px-3 py-2 text-xs text-muted-foreground">{t("common.none")}</p>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => {
          counter.current += 1;
          commit([...rows, { id: counter.current, key: "", value: "" }]);
        }}
      >
        <Plus />
        {addLabel ?? t("common.add")}
      </Button>
    </div>
  );
}

export function LabeledKeyValue({
  label,
  help,
  children,
}: {
  label: string;
  help?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        <Label>{label}</Label>
        {help ? <p className="text-xs leading-relaxed text-muted-foreground">{help}</p> : null}
      </div>
      {children}
    </div>
  );
}
