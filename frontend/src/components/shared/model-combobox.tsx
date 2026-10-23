import { Check, ChevronDown, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

interface ModelOption {
  name: string;
  vendor: string;
}

export function ModelCombobox({
  id,
  value,
  onChange,
  models,
  vendors,
  invalid = false,
  ariaDescribedBy,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  models: string[];
  vendors: Record<string, string>;
  invalid?: boolean;
  ariaDescribedBy?: string;
}) {
  const { t } = useTranslation();
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState(value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  const options = useMemo<ModelOption[]>(() => {
    const all = models.map((name) => ({ name, vendor: vendors[name] ?? "Otro" }));
    const needle = query.trim().toLocaleLowerCase();
    if (!needle) return all;
    return all.filter(
      (option) =>
        option.name.toLocaleLowerCase().includes(needle) ||
        option.vendor.toLocaleLowerCase().includes(needle),
    );
  }, [models, query, vendors]);

  const selectedVendor = value ? vendors[value] : undefined;
  const exactOption = options.findIndex(
    (option) => option.name.toLocaleLowerCase() === query.trim().toLocaleLowerCase(),
  );
  const exactKnown = exactOption >= 0;

  useEffect(() => {
    if (!open) return;
    setActive(exactOption >= 0 ? exactOption : options.length && query.trim() ? 0 : -1);
  }, [exactOption, open, options, query]);

  useEffect(() => {
    if (!open || active < 0) return;
    const row = listRef.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    row?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const anchor = rootRef.current?.getBoundingClientRect();
      if (!anchor) return;
      const margin = 6;
      const preferredHeight = 256;
      const spaceBelow = window.innerHeight - anchor.bottom - margin;
      const spaceAbove = anchor.top - margin;
      const openAbove = spaceBelow < 180 && spaceAbove > spaceBelow;
      setMenuStyle({
        position: "fixed",
        left: anchor.left,
        width: anchor.width,
        ...(openAbove
          ? { bottom: window.innerHeight - anchor.top + margin }
          : { top: anchor.bottom + margin }),
        maxHeight: Math.min(preferredHeight, Math.max(120, openAbove ? spaceAbove : spaceBelow)),
        zIndex: 100,
      });
    };
    updatePosition();
    const frame = window.requestAnimationFrame(updatePosition);
    const timer = window.setTimeout(updatePosition, 250);
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timer);
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    return () => document.removeEventListener("pointerdown", closeOnOutsidePointer);
  }, [open]);

  const canonicalModel = (raw: string) => models.find((model) => model.toLocaleLowerCase() === raw.toLocaleLowerCase());

  const commit = (next: string) => {
    setQuery(next);
    onChange(next);
    setOpen(false);
    inputRef.current?.focus();
  };

  const normalizeOnBlur = () => {
    const raw = query.trim();
    const canonical = canonicalModel(raw);
    if (canonical) {
      setQuery(canonical);
      onChange(canonical);
      return;
    }
    const label = /^([^\s(]+)\s*\(([^)]*)\)$/.exec(raw);
    if (label && models.includes(label[1]) && (vendors[label[1]] ?? "").toLocaleLowerCase() === label[2].toLocaleLowerCase()) {
      setQuery(label[1]);
      onChange(label[1]);
      return;
    }
    if (raw !== value) {
      setQuery(raw);
      onChange(raw);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((current) => Math.min(current + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActive((current) => Math.max(current - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (open && active >= 0 && options[active]) {
        commit(options[active].name);
      } else {
        commit(canonicalModel(query.trim()) ?? query.trim());
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className="relative">
      <div
        className={cn(
          "flex h-9 w-full items-center gap-1.5 rounded-md border border-input bg-card px-2.5 text-sm text-foreground shadow-xs transition-colors",
          "hover:border-input focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20",
          invalid && "border-destructive focus-within:border-destructive focus-within:ring-destructive/20",
        )}
      >
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <input
          ref={inputRef}
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && active >= 0 ? `${listId}-${active}` : undefined}
          aria-invalid={invalid}
          aria-describedby={ariaDescribedBy}
          autoComplete="off"
          spellCheck={false}
          value={query}
          placeholder={t("nodeForm.modelPlaceholder")}
          className="min-w-0 flex-1 bg-transparent py-1.5 font-mono text-xs outline-none placeholder:font-sans placeholder:text-muted-foreground/70"
          onChange={(event) => {
            const next = event.target.value;
            setQuery(next);
            onChange(next);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={normalizeOnBlur}
          onKeyDown={handleKeyDown}
        />
        {selectedVendor ? (
          <span className="shrink-0 text-[11px] text-muted-foreground">({selectedVendor})</span>
        ) : null}
        {query ? (
          <button
            type="button"
            className="rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            aria-label={t("common.clear")}
            title={t("common.clear")}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setQuery("");
              onChange("");
              setOpen(true);
              inputRef.current?.focus();
            }}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
        <button
          type="button"
          className="rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground"
          aria-label={t("nodeForm.model")}
          title={t("nodeForm.model")}
          tabIndex={-1}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => {
            setOpen((current) => !current);
            inputRef.current?.focus();
          }}
        >
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
        </button>
      </div>

      {open && menuStyle ? (
        <div
          ref={listRef}
          id={listId}
          role="listbox"
          aria-label={t("nodeForm.model")}
          style={menuStyle}
          className="overflow-y-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-lg"
        >
          {options.length ? (
            options.map((option, index) => {
              const selected = option.name === value;
              return (
                <button
                  key={option.name}
                  type="button"
                  role="option"
                  id={`${listId}-${index}`}
                  data-index={index}
                  aria-selected={selected}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => commit(option.name)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-xs transition-colors",
                    index === active ? "bg-accent text-accent-foreground" : "hover:bg-accent/60",
                  )}
                >
                  <span className="font-mono">{option.name}</span>
                  <span className="text-[11px] text-muted-foreground">({option.vendor})</span>
                  {selected ? <Check className="ml-auto h-3.5 w-3.5 text-primary" /> : null}
                </button>
              );
            })
          ) : (
            <div className="px-2 py-3 text-xs text-muted-foreground">{t("nodeForm.modelNoResults")}</div>
          )}
          {query.trim() && !exactKnown ? (
            <p className="border-t px-2 pb-1 pt-2 text-[10px] text-muted-foreground">
              {t("nodeForm.modelCustomHint")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
