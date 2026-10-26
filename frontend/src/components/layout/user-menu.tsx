import { LogOut, Settings2, UserRound } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { initials } from "@/lib/utils";

export function UserMenu() {
  const { t } = useTranslation();
  const { user, logout, can } = useAuth();
  const navigate = useNavigate();
  const [working, setWorking] = useState(false);
  if (!user) return null;

  const signOut = async () => {
    setWorking(true);
    try {
      await logout();
      toast.success(t("auth.loggedOut"));
      navigate("/login", { replace: true });
    } catch (error) {
      toast.error(t("errors.title"), { description: errorMessage(t, error) });
    } finally {
      setWorking(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="h-9 gap-2 rounded-lg px-1.5 text-muted-foreground hover:text-foreground sm:px-2"
          aria-label={t("nav.userMenu")}
        >
          <span className="flex h-7 w-7 items-center justify-center overflow-hidden rounded-md border border-primary/20 bg-primary/10 font-mono text-[10px] font-semibold text-primary">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
            ) : (
              initials(user.full_name || user.username)
            )}
          </span>
          <span className="hidden max-w-28 truncate text-xs font-medium text-foreground sm:block">
            {user.full_name || user.username}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="p-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground">{t("nav.userMenu")}</span>
            <span className="truncate text-sm font-semibold text-foreground">{user.full_name || user.username}</span>
            {user.full_name ? <span className="truncate text-[11px] text-muted-foreground">@{user.username}</span> : null}
            {user.email ? <span className="truncate text-[11px] text-muted-foreground">{user.email}</span> : null}
            <span className="text-[11px] font-normal text-muted-foreground">{t(`roles.${user.role}`)}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/profile")}>
          <UserRound />
          {t("nav.profile")}
        </DropdownMenuItem>
        {can("system.manage") ? (
          <DropdownMenuItem onSelect={() => navigate("/system")}>
            <Settings2 />
            {t("nav.system")}
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={working} onSelect={() => void signOut()} className="text-destructive focus:text-destructive">
          <LogOut />
          {t("nav.signOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
