import { ChevronDown, Variable } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { CatalogVar } from "@/types/api";

export function KnownVariables({ variables }: { variables: CatalogVar[] }) {
  const { t } = useTranslation();
  if (!variables.length) return null;
  return (
    <details className="group rounded-md border bg-muted/15">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-medium text-muted-foreground">
        <ChevronDown className="h-3 w-3 transition-transform group-open:rotate-180" />
        <Variable className="h-3.5 w-3.5" />
        {t("config.knownVariables")}
        <span className="ml-auto font-mono text-[9px] opacity-60">{variables.length}</span>
      </summary>
      <div className="max-h-56 space-y-2 overflow-y-auto border-t p-3">
        {variables.map((variable) => (
          <div key={variable.name} className="text-[11px]">
            <div className="flex flex-wrap items-baseline gap-1.5">
              <code className="font-mono text-[10px] text-foreground">{variable.name}</code>
              <span className="text-muted-foreground">{t(variable.label_code, { defaultValue: variable.name })}</span>
            </div>
            <p className="mt-0.5 leading-relaxed text-muted-foreground/80">
              {t(variable.help_code, { defaultValue: variable.technical_description })}
            </p>
          </div>
        ))}
      </div>
    </details>
  );
}
