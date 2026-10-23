import { useQueryClient } from "@tanstack/react-query";
import { FileText, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/shared/loaders";
import { useIntl } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ImportSummary } from "@/types/api";

const MAX_SIZE = 5_000_000;

export function NodeImportDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported?: () => void;
}) {
  const { t } = useTranslation();
  const intl = useIntl();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState("skip_existing");
  const [dryRun, setDryRun] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const choose = (candidate: File | null) => {
    setResult(null);
    setError(null);
    setFileError(null);
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".csv")) {
      setFileError(t("fileInput.invalidType"));
      return;
    }
    if (candidate.size > MAX_SIZE) {
      setFileError(t("fileInput.tooLarge"));
      return;
    }
    setFile(candidate);
  };

  const submit = async () => {
    if (!file) return;
    setSubmitting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mode", mode);
      formData.append("dry_run", String(dryRun));
      const summary = await api.importNodes(formData);
      setResult(summary);
      if (!dryRun) {
        await queryClient.invalidateQueries({ queryKey: ["nodes"] });
        await queryClient.invalidateQueries({ queryKey: ["status"] });
        await queryClient.invalidateQueries({ queryKey: ["jobs"] });
        onImported?.();
      }
    } catch (caught) {
      setError(errorMessage(t, caught));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("nodes.importTitle")}</DialogTitle>
          <DialogDescription>{t("nodes.importDescription")}</DialogDescription>
        </DialogHeader>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            choose(event.dataTransfer.files[0] ?? null);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-5 py-7 text-center transition-colors",
            dragging ? "border-primary bg-primary/[0.04]" : "border-border bg-muted/20 hover:border-primary/40 hover:bg-primary/[0.025]",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(event) => choose(event.target.files?.[0] ?? null)}
          />
          {file ? (
            <>
              <span className="mb-2 flex h-9 w-9 items-center justify-center rounded-md border bg-card text-primary">
                <FileText className="h-4 w-4" />
              </span>
              <span className="text-sm font-medium">{t("nodes.fileSelected", { name: file.name, size: formatBytes(file.size, intl.language) })}</span>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setFile(null);
                  setResult(null);
                }}
                className="mt-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-destructive"
              >
                <X className="h-3 w-3" />
                {t("common.remove")}
              </button>
            </>
          ) : (
            <>
              <UploadCloud className="mb-2 h-5 w-5 text-muted-foreground" />
              <span className="text-sm font-medium">{t("nodes.dropFile")}</span>
              <span className="mt-1 font-mono text-[10px] text-muted-foreground">CSV · 5 MB</span>
            </>
          )}
        </div>
        {fileError ? <p className="text-xs text-destructive">{fileError}</p> : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>{t("nodes.importMode")}</Label>
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="skip_existing">{t("nodes.importSkip")}</SelectItem>
                <SelectItem value="update_existing">{t("nodes.importUpdate")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <label className="flex cursor-pointer items-center gap-2 self-end rounded-md border bg-muted/20 px-3 py-2.5 text-xs">
            <Checkbox checked={dryRun} onCheckedChange={(checked) => setDryRun(Boolean(checked))} />
            {t("nodes.importDryRun")}
          </label>
        </div>

        {error ? (
          <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
            {error}
          </p>
        ) : null}

        {result ? (
          <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="success" className="normal-case tracking-normal">
                {t("nodes.importSummary", { created: result.created, updated: result.updated, skipped: result.skipped })}
              </Badge>
              {result.errors.length ? (
                <Badge variant="destructive" className="normal-case tracking-normal">
                  {t("nodes.importErrors", { count: result.errors.length })}
                </Badge>
              ) : null}
              {result.dry_run ? <Badge variant="outline">{t("nodes.importDryRun")}</Badge> : null}
            </div>
            {result.errors.length ? (
              <div className="max-h-40 overflow-auto rounded-md border bg-card">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-muted/90">
                    <tr>
                      <th className="px-2 py-1.5 text-left font-mono text-[9px] uppercase text-muted-foreground">{t("nodes.row")}</th>
                      <th className="px-2 py-1.5 text-left font-mono text-[9px] uppercase text-muted-foreground">{t("nodes.column")}</th>
                      <th className="px-2 py-1.5 text-left font-mono text-[9px] uppercase text-muted-foreground">{t("common.description")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.errors.map((item, index) => (
                      <tr key={index} className="border-t">
                        <td className="px-2 py-1.5 font-mono">{item.row}</td>
                        <td className="px-2 py-1.5 font-mono text-muted-foreground">{item.path ?? "—"}</td>
                        <td className="px-2 py-1.5 text-destructive">{t(`errors.${item.code}`, { ...item.params, defaultValue: item.code })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            {t("common.close")}
          </Button>
          <Button onClick={() => void submit()} disabled={!file || submitting}>
            {submitting ? <Spinner /> : <UploadCloud />}
            {dryRun ? t("nodes.importPreview") : t("nodes.importRun")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
