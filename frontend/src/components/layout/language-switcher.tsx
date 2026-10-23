import { Check, Globe2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { changeLanguage, currentLanguage } from "@/lib/i18n";

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const { meta, user, updateUser } = useAuth();
  const available = meta?.available_languages?.length ? meta.available_languages : ["es", "en"];
  const selected = currentLanguage();

  const select = async (language: string) => {
    if (language === selected) return;
    await changeLanguage(language, { persist: true });
    if (user) {
      try {
        const result = await api.updateMe({ language });
        updateUser(result.user);
      } catch (error) {
        toast.error(t("errors.title"), { description: errorMessage(t, error) });
      }
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "icon-sm" : "sm"}
          className="gap-1.5 text-muted-foreground"
          aria-label={t("common.language")}
          title={t("common.language")}
        >
          <Globe2 />
          {!compact ? <span className="font-mono text-[11px] uppercase">{selected}</span> : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel>{t("common.language")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {available.map((language) => (
          <DropdownMenuItem key={language} onSelect={() => void select(language)}>
            <span className="flex-1">{t(`languages.${language}`, { defaultValue: language.toUpperCase() })}</span>
            {selected === language ? <Check className="text-primary" /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
