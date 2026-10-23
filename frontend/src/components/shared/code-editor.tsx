import { basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { yaml } from "@codemirror/lang-yaml";
import { oneDark } from "@codemirror/theme-one-dark";
import { useEffect, useRef } from "react";

import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const baseTheme = EditorView.theme({
  "&": {
    backgroundColor: "transparent",
    color: "hsl(var(--foreground))",
    fontSize: "12px",
  },
  ".cm-content": {
    padding: "12px 0",
    caretColor: "hsl(var(--primary))",
  },
  ".cm-gutters": {
    backgroundColor: "transparent",
    borderRight: "1px solid hsl(var(--border))",
    color: "hsl(var(--muted-foreground) / .6)",
  },
  ".cm-activeLine": {
    backgroundColor: "hsl(var(--primary) / .05)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "hsl(var(--primary) / .05)",
  },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "hsl(var(--primary) / .16) !important",
  },
  ".cm-tooltip": {
    backgroundColor: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    color: "hsl(var(--popover-foreground))",
  },
  ".cm-line": {
    padding: "0 12px",
  },
  ".cm-scroller": {
    fontFamily: "JetBrains Mono Variable, ui-monospace, monospace",
    overflow: "auto",
  },
});

export function CodeEditor({
  value,
  onChange,
  readOnly = false,
  language = "yaml",
  className,
  minHeight = 200,
  maxHeight,
  ariaLabel,
}: {
  value: string;
  onChange?: (value: string) => void;
  readOnly?: boolean;
  language?: "yaml" | "text";
  className?: string;
  minHeight?: number;
  maxHeight?: number;
  ariaLabel?: string;
}) {
  const { resolvedTheme } = useTheme();
  const host = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const changeRef = useRef(onChange);
  changeRef.current = onChange;

  useEffect(() => {
    if (!host.current) return;
    const extensions = [
      basicSetup,
      EditorView.lineWrapping,
      baseTheme,
      EditorState.tabSize.of(2),
      EditorView.editable.of(!readOnly),
      EditorState.readOnly.of(readOnly),
      EditorView.contentAttributes.of({ "aria-label": ariaLabel ?? "" }),
      EditorView.updateListener.of((update) => {
        if (update.docChanged && changeRef.current) {
          changeRef.current(update.state.doc.toString());
        }
      }),
      ...(language === "yaml" ? [yaml()] : []),
      ...(resolvedTheme === "dark" ? [oneDark] : []),
    ];
    const view = new EditorView({
      state: EditorState.create({ doc: value, extensions }),
      parent: host.current,
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // The editor is intentionally recreated when theme/readOnly/language change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTheme, readOnly, language, ariaLabel]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    if (value !== view.state.doc.toString()) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: value },
      });
    }
  }, [value]);

  return (
    <div
      className={cn(
        "cm-host overflow-hidden rounded-md border bg-[#fbfcff] text-foreground shadow-xs dark:bg-[#0a101e]",
        className,
      )}
      style={{ minHeight, maxHeight, overflowY: maxHeight ? "auto" : undefined }}
    >
      <div ref={host} />
    </div>
  );
}
