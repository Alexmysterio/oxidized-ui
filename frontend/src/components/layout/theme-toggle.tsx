import { Check, Monitor, Moon, Sun } from "lucide-react";
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
import { useTheme } from "@/lib/theme";
import type { Theme } from "@/types/api";

const icons = { light: Sun, dark: Moon, system: Monitor } as const;

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const { user, updateUser } = useAuth();
  const Icon = icons[theme];

  const select = async (next: Theme) => {
    if (next === theme) return;
    const previous = theme;
    setTheme(next, { persist: true });
    if (user) {
      try {
        const result = await api.updateMe({ theme: next });
        updateUser(result.user);
      } catch (error) {
        setTheme(previous, { persist: true });
        toast.error(t("errors.title"), { description: errorMessage(t, error) });
      }
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size={compact ? "icon-sm" : "icon"}
          className="text-muted-foreground"
          aria-label={t("theme.toggle")}
          title={t("theme.toggle")}
        >
          <Icon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel>{t("common.theme")}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(["light", "dark", "system"] as Theme[]).map((option) => {
          const OptionIcon = icons[option];
          return (
            <DropdownMenuItem key={option} onSelect={() => void select(option)}>
              <OptionIcon />
              <span className="flex-1">{t(`theme.${option}`)}</span>
              {theme === option ? <Check className="text-primary" /> : null}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
