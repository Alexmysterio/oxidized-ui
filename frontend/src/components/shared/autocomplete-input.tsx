import {
  forwardRef,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type CSSProperties,
  type InputHTMLAttributes,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface AutocompleteInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "list"> {
  suggestions: string[];
  maxSuggestions?: number;
}

/**
 * Text input with an app-styled suggestion list.
 *
 * Unlike the native <datalist>, the menu inherits the console design, filters as
 * you type, supports keyboard navigation and portals outside scroll containers
 * so it is never clipped inside dialogs or side panels. Free text is preserved:
 * suggestions are optional.
 */
export const AutocompleteInput = forwardRef<HTMLInputElement, AutocompleteInputProps>(
  function AutocompleteInput(
    {
      suggestions,
      maxSuggestions = 50,
      className,
      onChange,
      onBlur,
      onFocus,
      onKeyDown,
      value,
      defaultValue,
      ...props
    },
    ref,
  ) {
    const listId = useId();
    const rootRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const listRef = useRef<HTMLDivElement>(null);
    const [query, setQuery] = useState(() => String(value ?? defaultValue ?? ""));
    const [open, setOpen] = useState(false);
    const [active, setActive] = useState(-1);
    const [menuStyle, setMenuStyle] = useState<CSSProperties | null>(null);

    useImperativeHandle(ref, () => inputRef.current as HTMLInputElement, []);

    useEffect(() => {
      if (value !== undefined) setQuery(String(value));
    }, [value]);

    const options = useMemo(() => {
      const unique = Array.from(new Set(suggestions.filter(Boolean)));
      const needle = query.trim().toLocaleLowerCase();
      const matches = needle
        ? unique.filter((item) => item.toLocaleLowerCase().includes(needle))
        : unique;
      return matches.slice(0, maxSuggestions);
    }, [maxSuggestions, query, suggestions]);

    const activeIndex = active >= 0 && active < options.length ? active : -1;

    useEffect(() => {
      if (!open) {
        setActive(-1);
        return;
      }
      setActive(options.length ? 0 : -1);
      // Only reset the highlight when the menu opens, not on every keystroke.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    useEffect(() => {
      if (!open) return;
      const updatePosition = () => {
        const anchor = rootRef.current?.getBoundingClientRect();
        if (!anchor) return;
        const margin = 6;
        const spaceBelow = window.innerHeight - anchor.bottom - margin;
        const spaceAbove = anchor.top - margin;
        const openAbove = spaceBelow < 160 && spaceAbove > spaceBelow;
        setMenuStyle({
          position: "fixed",
          left: anchor.left,
          width: anchor.width,
          ...(openAbove
            ? { bottom: window.innerHeight - anchor.top + margin }
            : { top: anchor.bottom + margin }),
          maxHeight: Math.min(240, Math.max(120, openAbove ? spaceAbove : spaceBelow)),
          zIndex: 120,
        });
      };
      updatePosition();
      const frame = window.requestAnimationFrame(updatePosition);
      window.addEventListener("resize", updatePosition);
      window.addEventListener("scroll", updatePosition, true);
      return () => {
        window.cancelAnimationFrame(frame);
        window.removeEventListener("resize", updatePosition);
        window.removeEventListener("scroll", updatePosition, true);
      };
    }, [open]);

    useEffect(() => {
      if (!open) return;
      const onPointerDown = (event: PointerEvent) => {
        const target = event.target as Node;
        if (rootRef.current?.contains(target) || listRef.current?.contains(target)) return;
        setOpen(false);
      };
      document.addEventListener("pointerdown", onPointerDown);
      return () => document.removeEventListener("pointerdown", onPointerDown);
    }, [open]);

    useEffect(() => {
      if (!open || activeIndex < 0) return;
      const row = listRef.current?.querySelector<HTMLElement>(`[data-index="${activeIndex}"]`);
      row?.scrollIntoView({ block: "nearest" });
    }, [activeIndex, open]);

    const setNativeValue = (next: string) => {
      const input = inputRef.current;
      if (!input) return;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, next);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    };

    const commit = (next: string) => {
      setNativeValue(next);
      setQuery(next);
      setOpen(false);
      setActive(-1);
      inputRef.current?.focus();
    };

    const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
      setQuery(event.target.value);
      setOpen(true);
      onChange?.(event);
    };

    const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setOpen(true);
        setActive((current) => Math.min(current + 1, options.length - 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setOpen(true);
        setActive((current) => Math.max(current - 1, 0));
      } else if (event.key === "Enter") {
        if (open && activeIndex >= 0 && options[activeIndex]) {
          event.preventDefault();
          commit(options[activeIndex]);
        }
      } else if (event.key === "Escape") {
        if (open) {
          event.preventDefault();
          event.stopPropagation();
        }
        setOpen(false);
        setActive(-1);
      } else if (event.key === "Tab") {
        setOpen(false);
      }
      onKeyDown?.(event);
    };

    const menu =
      open && options.length && menuStyle
        ? createPortal(
            <div
              ref={listRef}
              id={listId}
              role="listbox"
              style={menuStyle}
              onMouseDown={(event) => event.preventDefault()}
              className="overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-lift"
            >
              {options.map((option, index) => (
                <button
                  key={option}
                  type="button"
                  role="option"
                  id={`${listId}-${index}`}
                  data-index={index}
                  aria-selected={index === activeIndex}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => commit(option)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left font-mono text-xs transition-colors",
                    index === activeIndex ? "bg-accent text-accent-foreground" : "hover:bg-accent/60",
                  )}
                >
                  <span className="truncate">{option}</span>
                </button>
              ))}
            </div>,
            document.body,
          )
        : null;

    return (
      <div ref={rootRef} className="relative">
        <Input
          {...props}
          ref={inputRef}
          value={value}
          defaultValue={value === undefined ? defaultValue : undefined}
          className={className}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          autoComplete="off"
          onChange={handleChange}
          onFocus={(event) => {
            setQuery(inputRef.current?.value ?? "");
            setOpen(true);
            onFocus?.(event);
          }}
          onBlur={(event) => {
            setOpen(false);
            setActive(-1);
            onBlur?.(event);
          }}
          onKeyDown={handleKeyDown}
        />
        {menu}
      </div>
    );
  },
);

AutocompleteInput.displayName = "AutocompleteInput";
