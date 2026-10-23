import { Plus, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

export interface MapEntry {
  match: string;
  target: string;
  is_regex: boolean;
}

function normalize(value: unknown): MapEntry[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => ({
      match: String(item.match ?? ""),
      target: String(item.target ?? ""),
      is_regex: Boolean(item.is_regex),
    }));
}

export function MapListEditor({
  value,
  onChange,
  title,
  help,
  className,
}: {
  value: unknown;
  onChange: (value: MapEntry[]) => void;
  title: string;
  help?: string;
  className?: string;
}) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<MapEntry[]>(() => normalize(value));
  const lastSerialized = useRef(JSON.stringify(rows));
  useEffect(() => {
    const incoming = JSON.stringify(normalize(value));
    if (incoming !== lastSerialized.current) {
      const next = normalize(value);
      setRows(next);
      lastSerialized.current = incoming;
    }
  }, [value]);

  const commit = (next: MapEntry[]) => {
    const cleaned = next.filter((entry) => entry.match.trim() && entry.target.trim());
    setRows(next);
    lastSerialized.current = JSON.stringify(cleaned);
    onChange(cleaned);
  };

  return (
    <div className={cn("space-y-3", className)}>
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <Label className="font-mono text-xs">{title}</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => commit([...rows, { match: "", target: "", is_regex: false }])}
          >
            <Plus />
            {t("config.addMapping")}
          </Button>
        </div>
        {help ? <p className="text-xs leading-relaxed text-muted-foreground">{help}</p> : null}
      </div>
      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed px-3 py-3 text-xs text-muted-foreground">{t("common.none")}</p>
      ) : (
        <div className="space-y-2">
          {rows.map((row, index) => (
            <div key={index} className="grid gap-2 rounded-md border bg-muted/20 p-2 sm:grid-cols-[1.2fr_1.2fr_auto_auto] sm:items-center">
              <Input
                value={row.match}
                placeholder={t("config.match")}
                aria-label={t("config.match")}
                className="font-mono text-xs"
                onChange={(event) => {
                  const next = rows.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, match: event.target.value } : item,
                  );
                  commit(next);
                }}
              />
              <Input
                value={row.target}
                placeholder={t("config.target")}
                aria-label={t("config.target")}
                className="font-mono text-xs"
                onChange={(event) => {
                  const next = rows.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, target: event.target.value } : item,
                  );
                  commit(next);
                }}
              />
              <label className="flex items-center gap-2 text-[11px] text-muted-foreground">
                <Switch
                  checked={row.is_regex}
                  onCheckedChange={(checked) => {
                    const next = rows.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, is_regex: checked } : item,
                    );
                    commit(next);
                  }}
                  aria-label={t("config.regex")}
                />
                {t("config.regex")}
              </label>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={t("common.remove")}
                onClick={() => commit(rows.filter((_, itemIndex) => itemIndex !== index))}
              >
                <X />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
