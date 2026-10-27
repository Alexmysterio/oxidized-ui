import {
  Activity,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileCode2,
  Gauge,
  GitCompareArrows,
  Network,
  Scale,
  ScrollText,
  Server,
  ServerCog,
  Settings2,
  ShieldCheck,
  UsersRound,
  Wrench,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

import { BrandLockup } from "@/components/shared/brand";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  labelKey: string;
  icon: LucideIcon;
  capability?: string;
  end?: boolean;
}

interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

const groups: NavGroup[] = [
  {
    labelKey: "nav.overview",
    items: [{ to: "/", labelKey: "nav.dashboard", icon: Gauge, end: true }],
  },
  {
    labelKey: "nav.inventory",
    items: [
      { to: "/nodes", labelKey: "nav.nodes", icon: Network, capability: "nodes.read" },
      { to: "/node-templates", labelKey: "nav.nodeTemplates", icon: Server, capability: "nodes.read" },
      { to: "/reconciliation", labelKey: "nav.reconciliation", icon: GitCompareArrows, capability: "nodes.read" },
      { to: "/groups", labelKey: "nav.groups", icon: UsersRound, capability: "groups.write" },
    ],
  },
  {
    labelKey: "nav.operations",
    items: [
      { to: "/config", labelKey: "nav.config", icon: FileCode2, capability: "config.read" },
      { to: "/backups", labelKey: "nav.backups", icon: CalendarClock, capability: "backups.trigger" },
      { to: "/maintenance", labelKey: "nav.maintenance", icon: Wrench, capability: "backups.trigger" },
      { to: "/compliance", labelKey: "nav.compliance", icon: Scale, capability: "compliance.read" },
      { to: "/status", labelKey: "nav.status", icon: Activity, capability: "logs.read" },
    ],
  },
  {
    labelKey: "nav.administration",
    items: [
      { to: "/users", labelKey: "nav.users", icon: ShieldCheck, capability: "users.manage" },
      { to: "/audit", labelKey: "nav.audit", icon: ScrollText, capability: "audit.read" },
      { to: "/system", labelKey: "nav.system", icon: Settings2, capability: "system.manage" },
    ],
  },
];

function NavEntry({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const { t } = useTranslation();
  const Icon = item.icon;
  const link = (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "group relative flex h-9 items-center gap-2.5 rounded-md px-2.5 text-[13px] font-medium transition-colors",
          collapsed && "justify-center px-0",
          isActive
            ? "bg-white/[0.07] text-sidebar-foreground"
            : "text-sidebar-muted hover:bg-white/[0.04] hover:text-sidebar-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              "absolute left-0 h-4 w-0.5 rounded-full bg-primary opacity-0 transition-opacity",
              isActive && "opacity-100",
            )}
          />
          <Icon className={cn("h-[17px] w-[17px] shrink-0", isActive ? "text-primary" : "opacity-75")} strokeWidth={1.8} />
          {!collapsed ? <span className="truncate">{t(item.labelKey)}</span> : null}
        </>
      )}
    </NavLink>
  );

  if (!collapsed) return link;
  return (
    <Tooltip delayDuration={150}>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{t(item.labelKey)}</TooltipContent>
    </Tooltip>
  );
}

export function SidebarContent({
  collapsed = false,
  onToggle,
  onNavigate,
  onClose,
  mobile = false,
}: {
  collapsed?: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
  onClose?: () => void;
  mobile?: boolean;
}) {
  const { t } = useTranslation();
  const { can, user, meta } = useAuth();
  return (
    <div className="sidebar-grid flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className={cn("flex h-16 items-center border-b border-sidebar-border px-4", collapsed && "justify-center px-2")}>
        <NavLink to="/" onClick={onNavigate} aria-label={t("nav.dashboard")} className="min-w-0">
          <BrandLockup compact={collapsed} />
        </NavLink>
        {!mobile && onToggle ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            onClick={onToggle}
            className={cn("ml-auto text-sidebar-muted hover:bg-white/[0.06] hover:text-sidebar-foreground", collapsed && "ml-1 h-6 w-6")}
            aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
            title={collapsed ? t("nav.expand") : t("nav.collapse")}
          >
            {collapsed ? <ChevronRight /> : <ChevronLeft />}
          </Button>
        ) : null}
        {mobile && onClose ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            className="ml-auto text-sidebar-muted hover:bg-white/[0.06] hover:text-sidebar-foreground"
            aria-label={t("nav.closeMenu")}
          >
            <X />
          </Button>
        ) : null}
      </div>

      <nav aria-label={t("nav.mainNavigation")} className="flex-1 overflow-y-auto px-2 py-5">
        <div className="space-y-5">
          {groups.map((group) => {
            const items = group.items.filter((item) => !item.capability || can(item.capability));
            if (items.length === 0) return null;
            return (
              <div key={group.labelKey}>
                {!collapsed ? (
                  <p className="mb-1.5 px-2.5 font-mono text-[9px] uppercase tracking-[0.18em] text-sidebar-muted/70">
                    {t(group.labelKey)}
                  </p>
                ) : (
                  <div className="mx-auto mb-2 h-px w-5 bg-sidebar-border" />
                )}
                <div className="space-y-0.5">
                  {items.map((item) => (
                    <NavEntry key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </nav>

      <div className={cn("border-t border-sidebar-border p-3", collapsed && "px-2")}>
        {collapsed ? (
          <Tooltip delayDuration={150}>
            <TooltipTrigger asChild>
              <NavLink
                to="/profile"
                onClick={onNavigate}
                className="mx-auto flex h-8 w-8 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] font-mono text-[10px] text-sidebar-foreground"
                aria-label={t("nav.profile")}
              >
                {user?.username.slice(0, 2).toUpperCase()}
              </NavLink>
            </TooltipTrigger>
            <TooltipContent side="right">
              {user?.username} · {user ? t(`roles.${user.role}`) : ""}
            </TooltipContent>
          </Tooltip>
        ) : (
          <NavLink
            to="/profile"
            onClick={onNavigate}
            className="flex items-center gap-2.5 rounded-md p-1.5 transition-colors hover:bg-white/[0.05]"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-md border border-white/10 bg-white/[0.05] font-mono text-[10px] text-sidebar-foreground">
              {user?.username.slice(0, 2).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-sidebar-foreground">{user?.username}</span>
              <span className="block truncate text-[10px] text-sidebar-muted">
                {user ? t(`roles.${user.role}`) : ""}
              </span>
            </span>
            <ClipboardList className="h-3.5 w-3.5 text-sidebar-muted/50" />
          </NavLink>
        )}
        {!collapsed ? (
          <div className="mt-3 flex items-center justify-between border-t border-sidebar-border pt-2.5">
            <span className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.14em] text-sidebar-muted/70">
              <ServerCog className="h-3 w-3" />
              {t("app.version")} {meta?.app_version ?? "0.1.0"}
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_8px_hsl(var(--success))]" />
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 hidden border-r border-sidebar-border transition-[width] duration-200 lg:block",
        collapsed ? "w-20" : "w-[268px]",
      )}
    >
      <SidebarContent collapsed={collapsed} onToggle={onToggle} />
    </aside>
  );
}
