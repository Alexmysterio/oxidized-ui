import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Map as MapIcon, MapPin, Network, Pencil, Search, ServerCog } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Spinner } from "@/components/shared/loaders";
import { NodeStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SiteMap } from "@/features/sites/site-map";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { NodeStatus, SiteGroup } from "@/types/api";

type LocatedSite = SiteGroup & { latitude: number; longitude: number };

interface SitePayload {
  site: string;
  coordinates: string | null;
  owner: string | null;
  contact: string | null;
  notes: string | null;
  reviewed: boolean;
}

function formatCoordinates(site: SiteGroup): string {
  return `${Number(site.latitude).toFixed(5)}, ${Number(site.longitude).toFixed(5)}`;
}

export function SitesPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [tag, setTag] = useState("Site");
  const [search, setSearch] = useState("");
  const [editingSite, setEditingSite] = useState<SiteGroup | null>(null);
  const [coordinates, setCoordinates] = useState("");
  const [owner, setOwner] = useState("");
  const [contact, setContact] = useState("");
  const [notes, setNotes] = useState("");
  const [reviewed, setReviewed] = useState(false);
  usePageTitle("nav.sites");

  const tagsQuery = useQuery({ queryKey: ["node-tags"], queryFn: api.nodeTags });
  const sitesQuery = useQuery({ queryKey: ["sites", tag], queryFn: () => api.sites(tag) });
  const tagKeys = Array.from(new Set(["Site", ...(tagsQuery.data?.items ?? []).map((item) => item.key)]));
  const sites = sitesQuery.data?.sites ?? [];
  const needle = search.trim().toLocaleLowerCase();
  const filteredSites = needle
    ? sites.filter((site) =>
        [site.name, site.owner, site.contact, site.notes]
          .filter(Boolean)
          .join(" ")
          .toLocaleLowerCase()
          .includes(needle),
      )
    : sites;
  const mapped = filteredSites.filter(
    (site): site is LocatedSite => typeof site.latitude === "number" && typeof site.longitude === "number",
  );

  const updateSite = useMutation({
    mutationFn: (payload: SitePayload) => api.updateSite(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sites"] });
      toast.success(t("sites.updated"));
      setEditingSite(null);
    },
    onError: (error) => notifyError(t, error),
  });

  const backupSite = useMutation({
    mutationFn: (site: SiteGroup) =>
      api.bulkNodes({ action: "backup", ids: site.nodes.map((node) => node.id) }),
    onSuccess: (_result, site) => {
      toast.success(t("sites.backupQueued", { count: site.count }));
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["status"] });
      void queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const openEditor = (site: SiteGroup) => {
    setEditingSite(site);
    setCoordinates(site.latitude != null && site.longitude != null ? formatCoordinates(site) : "");
    setOwner(site.owner ?? "");
    setContact(site.contact ?? "");
    setNotes(site.notes ?? "");
    setReviewed(false);
  };

  const submit = () => {
    if (!editingSite?.name) return;
    updateSite.mutate({
      site: editingSite.name,
      coordinates: coordinates.trim() || null,
      owner: owner.trim() || null,
      contact: contact.trim() || null,
      notes: notes.trim() || null,
      reviewed,
    });
  };

  const clearCoordinates = () => {
    if (!editingSite?.name) return;
    updateSite.mutate({
      site: editingSite.name,
      coordinates: null,
      owner: owner.trim() || null,
      contact: contact.trim() || null,
      notes: notes.trim() || null,
      reviewed: false,
    });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><MapIcon className="h-3.5 w-3.5 text-primary" />{t("nav.inventory")}</>}
        title={t("sites.title")}
        description={t("sites.subtitle")}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("sites.searchPlaceholder")}
                className="h-8 w-56 pl-8 text-xs"
              />
            </div>
            <Select value={tag} onValueChange={setTag}>
              <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                {tagKeys.map((key) => (
                  <SelectItem key={key} value={key}>{t("sites.tagBy", { tag: key })}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />

      {sitesQuery.isError ? (
        <ErrorState onRetry={() => void sitesQuery.refetch()} />
      ) : !sites.length ? (
        <EmptyState icon={MapPin} title={t("sites.emptyTitle")} description={t("sites.emptyDescription")} />
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("sites.map")}</CardTitle>
              <CardDescription>{t("sites.mapDescription")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {mapped.length ? (
                <SiteMap
                  sites={mapped}
                  onBackup={can("backups.trigger") ? (site) => backupSite.mutate(site) : undefined}
                />
              ) : (
                <p className="rounded-md border border-dashed px-3 py-8 text-center text-xs text-muted-foreground">
                  {t("sites.mapEmpty")}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">{t("sites.mapHelp")}</p>
            </CardContent>
          </Card>

          {filteredSites.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {filteredSites.map((site) => (
                <Card key={site.name ?? "__none__"}>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                      <MapPin className="h-4 w-4 text-primary" />
                      <span className="min-w-0 truncate">{site.name ?? t("sites.noSite")}</span>
                      <Badge variant="outline" className="ml-auto">{t("sites.nodes", { count: site.count })}</Badge>
                      {can("backups.trigger") ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          onClick={() => backupSite.mutate(site)}
                          disabled={backupSite.isPending}
                          title={t("sites.backup")}
                          aria-label={t("sites.backup")}
                        >
                          {backupSite.isPending ? <Spinner /> : <ServerCog />}
                        </Button>
                      ) : null}
                      {can("nodes.write") && site.name ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-xs"
                          onClick={() => openEditor(site)}
                          title={t("sites.editSite")}
                          aria-label={t("sites.editSite")}
                        >
                          <Pencil />
                        </Button>
                      ) : null}
                    </CardTitle>
                    <p className="font-mono text-[10px] text-muted-foreground">
                      {site.latitude != null && site.longitude != null
                        ? formatCoordinates(site)
                        : t("sites.noCoordinates")}
                    </p>
                    {site.owner ? (
                      <p className="truncate text-[11px] text-muted-foreground">
                        <span className="font-medium text-foreground">{t("sites.owner")}:</span> {site.owner}
                      </p>
                    ) : null}
                    {site.contact ? (
                      <p className="truncate text-[11px] text-muted-foreground">
                        <span className="font-medium text-foreground">{t("sites.contact")}:</span> {site.contact}
                      </p>
                    ) : null}
                    {site.notes ? <p className="line-clamp-2 text-[11px] text-muted-foreground">{site.notes}</p> : null}
                    <p className="text-[10px] text-muted-foreground">
                      {site.last_reviewed_at
                        ? t("sites.reviewedAt", { when: intl.relative(site.last_reviewed_at) })
                        : t("sites.notReviewed")}
                    </p>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {Object.entries(site.status).map(([status, count]) => (
                        <span key={status} className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground">
                          {t(`nodeStatus.${status as NodeStatus}`)}: {count}
                        </span>
                      ))}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-1">
                    {site.nodes.map((node) => (
                      <Link
                        key={node.id}
                        to={`/nodes/${node.id}`}
                        className={cn("flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-muted/50")}
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <Network className="h-3 w-3 shrink-0 text-muted-foreground" />
                          <span className="truncate font-medium">{node.name}</span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          <span className="font-mono text-[10px] text-muted-foreground">{node.group_name ?? "—"}</span>
                          <NodeStatusBadge status={node.status} />
                        </span>
                      </Link>
                    ))}
                  </CardContent>
                </Card>
              ))}
            </div>
          ) : (
            <p className="rounded-md border border-dashed px-3 py-8 text-center text-xs text-muted-foreground">
              {t("sites.noMatches")}
            </p>
          )}
        </>
      )}

      <Dialog open={editingSite !== null} onOpenChange={(open) => { if (!open) setEditingSite(null); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>{t("sites.editSiteTitle", { site: editingSite?.name ?? "" })}</DialogTitle>
            <DialogDescription>{t("sites.editSiteDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="site-coordinates">{t("sites.coordinates")}</Label>
              <Input
                id="site-coordinates"
                value={coordinates}
                onChange={(event) => setCoordinates(event.target.value)}
                placeholder="36.751112, -3.491751"
                autoFocus
              />
              <p className="text-[11px] leading-relaxed text-muted-foreground">{t("sites.coordinatesHelp")}</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="site-owner">{t("sites.owner")}</Label>
                <Input id="site-owner" value={owner} onChange={(event) => setOwner(event.target.value)} maxLength={128} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="site-contact">{t("sites.contact")}</Label>
                <Input id="site-contact" value={contact} onChange={(event) => setContact(event.target.value)} maxLength={128} />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="site-notes">{t("sites.notes")}</Label>
              <Textarea id="site-notes" value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} maxLength={2000} />
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
              <Checkbox checked={reviewed} onCheckedChange={(checked) => setReviewed(Boolean(checked))} />
              {t("sites.markReviewed")}
            </label>
            <p className="text-[11px] text-muted-foreground">
              {editingSite?.last_reviewed_at
                ? t("sites.reviewedAt", { when: intl.relative(editingSite.last_reviewed_at) })
                : t("sites.notReviewed")}
            </p>
          </div>
          <DialogFooter>
            {editingSite?.latitude != null ? (
              <Button type="button" variant="outline" onClick={clearCoordinates} disabled={updateSite.isPending}>
                {t("sites.clearCoordinates")}
              </Button>
            ) : null}
            <Button type="button" variant="outline" onClick={() => setEditingSite(null)} disabled={updateSite.isPending}>
              {t("common.cancel")}
            </Button>
            <Button type="button" onClick={submit} disabled={updateSite.isPending}>
              {updateSite.isPending ? <Spinner /> : null}
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
