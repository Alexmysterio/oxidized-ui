import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { copyToClipboard } from "@/lib/utils";

export function CopyButton({ value, className, label }: { value: string; className?: string; label?: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className={className}
      aria-label={label ?? t("common.copy")}
      title={label ?? t("common.copy")}
      onClick={async () => {
        try {
          await copyToClipboard(value);
          setCopied(true);
          toast.success(t("common.copied"), { description: t("common.copiedDescription") });
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          toast.error(t("common.copyFailed"));
        }
      }}
    >
      {copied ? <Check className="text-success" /> : <Copy />}
    </Button>
  );
}
