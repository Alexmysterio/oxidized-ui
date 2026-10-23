import { Menu, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";

import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";

function titleKey(pathname: string): string {
  if (pathname === "/") return "nav.dashboard";
  if (pathname.startsWith("/nodes")) return "nav.nodes";
  if (pathname.startsWith("/groups")) return "nav.groups";
  if (pathname.startsWith("/config")) return "nav.config";
  if (pathname.startsWith("/status")) return "nav.status";
  if (pathname.startsWith("/users")) return "nav.users";
  if (pathname.startsWith("/audit")) return "nav.audit";
  if (pathname.startsWith("/profile")) return "nav.profile";
  if (pathname.startsWith("/system")) return "nav.system";
  return "nav.dashboard";
}

export function Topbar({
  onOpenMenu,
  onOpenSearch,
}: {
  onOpenMenu: () => void;
  onOpenSearch: () => void;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const title = t(titleKey(location.pathname));
  return (
    <header className="sticky top-0 z-30 border-b border-border/70 bg-background/80 backdrop-blur-xl">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 xl:px-8">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="lg:hidden"
          onClick={onOpenMenu}
          aria-label={t("nav.openMenu")}
        >
          <Menu />
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="hidden h-1.5 w-1.5 rounded-full bg-primary sm:block" />
            <span className="truncate text-sm font-semibold tracking-tight">{title}</span>
          </div>
          <p className="hidden font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground sm:block">
            {t("app.tagline")}
          </p>
        </div>

        <button
          type="button"
          onClick={onOpenSearch}
          className="group ml-auto hidden h-9 w-full max-w-[19rem] items-center gap-2 rounded-md border border-border/80 bg-card/80 px-3 text-left text-xs text-muted-foreground shadow-xs transition-colors hover:border-foreground/15 hover:text-foreground md:flex"
          aria-label={t("nav.search")}
        >
          <Search className="h-3.5 w-3.5" />
          <span className="flex-1 truncate">{t("nav.search")}</span>
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[9px] tracking-wide text-muted-foreground">
            {t("search.shortcut")}
          </kbd>
        </button>

        <div className="ml-auto flex items-center gap-0.5 md:ml-0">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            onClick={onOpenSearch}
            aria-label={t("nav.search")}
          >
            <Search />
          </Button>
          <LanguageSwitcher compact />
          <ThemeToggle compact />
          <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
