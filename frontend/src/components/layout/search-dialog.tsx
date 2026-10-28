import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowUpRight,
  CalendarClock,
  FileCode2,
  Gauge,
  GitCompareArrows,
  Loader2,
  MapPin,
  Network,
  Scale,
  Search,
  ScrollText,
  Server,
  Settings2,
  ShieldCheck,
  UserRound,
  UsersRound,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/errors";
import { cn } from "@/lib/utils";

interface PageResult {
  labelKey: string;
  to: string;
  icon: LucideIcon;
  capability?: string;
}

const pages: PageResult[] = [
  { labelKey: "nav.dashboard", to: "/", icon: Gauge },
  { labelKey: "nav.nodes", to: "/nodes", icon: Network, capability: "nodes.read" },
  { labelKey: "nav.nodeTemplates", to: "/node-templates", icon: Server, capability: "nodes.write" },
  { labelKey: "nav.reconciliation", to: "/reconciliation", icon: GitCompareArrows, capability: "nodes.read" },
  { labelKey: "nav.sites", to: "/sites", icon: MapPin, capability: "nodes.read" },
  { labelKey: "nav.groups", to: "/groups", icon: UsersRound, capability: "groups.write" },
  { labelKey: "nav.config", to: "/config", icon: FileCode2, capability: "config.read" },
  { labelKey: "nav.backups", to: "/backups", icon: CalendarClock, capability: "backups.trigger" },
  { labelKey: "nav.maintenance", to: "/maintenance", icon: Wrench, capability: "backups.trigger" },
  { labelKey: "nav.compliance", to: "/compliance", icon: Scale, capability: "compliance.read" },
  { labelKey: "nav.status", to: "/status", icon: Activity, capability: "logs.read" },
  { labelKey: "nav.users", to: "/users", icon: ShieldCheck, capability: "users.manage" },
  { labelKey: "nav.audit", to: "/audit", icon: ScrollText, capability: "audit.read" },
  { labelKey: "nav.system", to: "/system", icon: Settings2, capability: "system.manage" },
  { labelKey: "nav.profile", to: "/profile", icon: UserRound },
];

export function SearchDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { can } = useAuth();
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"inventory" | "configs">("inventory");
  const debounced = useDebounce(query.trim(), 250);
  const [configSubmitted, setConfigSubmitted] = useState("");

  const searchQuery = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced),
    enabled: open && mode === "inventory" && debounced.length >= 2,
    staleTime: 10_000,
  });

  const configSearch = useMutation({
    mutationFn: (value: string) => api.searchConfigs(value),
  });

  useEffect(() => {
    if (!open) {
      setQuery("");
      setMode("inventory");
      setConfigSubmitted("");
      configSearch.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const pageResults = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    return pages.filter(
      (page) =>
        (!page.capability || can(page.capability)) &&
        (!needle || t(page.labelKey).toLocaleLowerCase().includes(needle)),
    );
  }, [query, can, t]);

  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  const submitConfigSearch = () => {
    const trimmed = query.trim();
    if (trimmed.length < 2) return;
    setConfigSubmitted(trimmed);
    configSearch.mutate(trimmed);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[10%] max-w-2xl translate-y-0 gap-0 overflow-hidden p-0">
        <DialogHeader className="sr-only">
          <DialogTitle>{t("search.title")}</DialogTitle>
          <DialogDescription>{t("search.hint")}</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2 border-b px-3">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && mode === "configs") submitConfigSearch();
            }}
            placeholder={mode === "inventory" ? t("search.placeholder") : t("search.configSearchPlaceholder")}
            className="h-12 flex-1 border-0 bg-transparent px-0 text-base shadow-none focus-visible:ring-0"
          />
          {configSearch.isPending ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
        </div>
        <div className="flex items-center gap-1 border-b bg-muted/25 px-3 py-1.5">
          <button
            type="button"
            onClick={() => setMode("inventory")}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              mode === "inventory" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("search.inventory")}
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("configs");
              setConfigSubmitted("");
              configSearch.reset();
            }}
            className={cn(
              "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              mode === "configs" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t("search.configSearch")}
          </button>
          <span className="ml-auto hidden font-mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground sm:block">
            {t("search.shortcut")}
          </span>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {mode === "inventory" ? (
            <>
              {debounced.length >= 2 ? (
                <div className="mb-2">
                  <p className="px-2 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                    {t("search.nodes")}
                  </p>
                  {searchQuery.isLoading ? (
                    <div className="space-y-1 p-2">
                      <Skeleton className="h-9 w-full" />
                      <Skeleton className="h-9 w-full" />
                    </div>
                  ) : searchQuery.data?.nodes?.length ? (
                    searchQuery.data.nodes.map((node) => (
                      <button
                        key={node.id}
                        type="button"
                        onClick={() => go(`/nodes/${node.id}`)}
                        className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary"
                      >
                        <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card text-primary">
                          <Network className="h-3.5 w-3.5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{node.name}</span>
                          <span className="block truncate font-mono text-[10px] text-muted-foreground">
                            {node.address ?? "—"} · {node.model} {node.group_name ? `· ${node.group_name}` : ""}
                          </span>
                        </span>
                        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    ))
                  ) : (
                    <p className="px-2 py-3 text-xs text-muted-foreground">{t("search.noResults")}</p>
                  )}
                </div>
              ) : null}

              {can("groups.write") && searchQuery.data?.groups?.length ? (
                <div className="mb-2">
                  <p className="px-2 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                    {t("search.groups")}
                  </p>
                  {searchQuery.data.groups.map((group) => (
                    <button
                      key={group.name}
                      type="button"
                      onClick={() => go("/groups")}
                      className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary"
                    >
                      <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card text-primary">
                        <UsersRound className="h-3.5 w-3.5" />
                      </span>
                      <span className="flex-1 truncate text-sm">{group.name}</span>
                      <Badge variant="outline">{t("search.groups")}</Badge>
                    </button>
                  ))}
                </div>
              ) : null}

              <div>
                <p className="px-2 py-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                  {t("search.pages")}
                </p>
                {pageResults.length ? (
                  pageResults.map((page) => {
                    const Icon = page.icon;
                    return (
                      <button
                        key={page.to}
                        type="button"
                        onClick={() => go(page.to)}
                        className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary"
                      >
                        <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card text-muted-foreground">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <span className="flex-1 text-sm">{t(page.labelKey)}</span>
                        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    );
                  })
                ) : (
                  <p className="px-2 py-3 text-xs text-muted-foreground">{t("search.noResults")}</p>
                )}
              </div>
            </>
          ) : (
            <div className="p-2">
              <p className="mb-3 max-w-lg text-xs leading-relaxed text-muted-foreground">{t("search.configSearchHint")}</p>
              <Button
                size="sm"
                onClick={submitConfigSearch}
                disabled={query.trim().length < 2 || configSearch.isPending}
              >
                {configSearch.isPending ? <Loader2 className="animate-spin" /> : <Search />}
                {t("common.search")}
              </Button>
              <div className="mt-4">
                {configSearch.isError ? (
                  <p className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
                    {errorMessage(t, configSearch.error)}
                  </p>
                ) : configSubmitted && configSearch.data ? (
                  configSearch.data.matches.length ? (
                    <>
                      <p className="mb-1 px-1 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
                        {t("search.configSearchResults")}
                      </p>
                      {configSearch.data.matches.map((match) => (
                        <button
                          key={match.node_id}
                          type="button"
                          onClick={() => go(`/nodes/${match.node_id}`)}
                          className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary"
                        >
                          <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-card text-primary">
                            <Network className="h-3.5 w-3.5" />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm">{match.name}</span>
                            <span className="block truncate font-mono text-[10px] text-muted-foreground">
                              {match.model} {match.group_name ? `· ${match.group_name}` : ""}
                            </span>
                          </span>
                          <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground" />
                        </button>
                      ))}
                    </>
                  ) : (
                    <p className="py-6 text-center text-xs text-muted-foreground">{t("search.configSearchEmpty")}</p>
                  )
                ) : null}
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
