import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Map as MapIcon, MapPin, Network, Pencil } from "lucide-react";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SiteMap } from "@/features/sites/site-map";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { NodeStatus, SiteGroup } from "@/types/api";

type LocatedSite = SiteGroup & { latitude: number; longitude: number };

function formatCoordinates(site: SiteGroup): string {
  return `${Number(site.latitude).toFixed(5)}, ${Number(site.longitude).toFixed(5)}`;
}

export function SitesPage() {
  const { t } = useTranslation();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [tag, setTag] = useState("Site");
  const [editingSite, setEditingSite] = useState<SiteGroup | null>(null);
  const [coordinates, setCoordinates] = useState("");
  usePageTitle("nav.sites");

  const tagsQuery = useQuery({ queryKey: ["node-tags"], queryFn: api.nodeTags });
  const sitesQuery = useQuery({ queryKey: ["sites", tag], queryFn: () => api.sites(tag) });
  const tagKeys = Array.from(new Set(["Site", ...(tagsQuery.data?.items ?? []).map((item) => item.key)]));
  const sites = sitesQuery.data?.sites ?? [];
  const mapped = sites.filter(
    (site): site is LocatedSite => typeof site.latitude === "number" && typeof site.longitude === "number",
  );

  const saveCoordinates = useMutation({
    mutationFn: ({ site, value }: { site: string; value: string | null }) => api.setSiteCoordinates(site, value),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["sites"] });
      toast.success(variables.value ? t("sites.coordinatesSaved") : t("sites.coordinatesCleared"));
      setEditingSite(null);
    },
    onError: (error) => notifyError(t, error),
  });

  const openEditor = (site: SiteGroup) => {
    setEditingSite(site);
    setCoordinates(site.latitude != null && site.longitude != null ? formatCoordinates(site) : "");
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><MapIcon className="h-3.5 w-3.5 text-primary" />{t("nav.inventory")}</>}
        title={t("sites.title")}
        description={t("sites.subtitle")}
        actions={
          <Select value={tag} onValueChange={setTag}>
            <SelectTrigger className="h-8 w-48 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {tagKeys.map((key) => (
                <SelectItem key={key} value={key}>{t("sites.tagBy", { tag: key })}</SelectItem>
              ))}
            </SelectContent>
          </Select>
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
                <SiteMap sites={mapped} />
              ) : (
                <p className="rounded-md border border-dashed px-3 py-8 text-center text-xs text-muted-foreground">
                  {t("sites.mapEmpty")}
                </p>
              )}
              <p className="text-[11px] text-muted-foreground">{t("sites.mapHelp")}</p>
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sites.map((site) => (
              <Card key={site.name ?? "__none__"}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
                    <MapPin className="h-4 w-4 text-primary" />
                    <span className="min-w-0 truncate">{site.name ?? t("sites.noSite")}</span>
                    <Badge variant="outline" className="ml-auto">{t("sites.nodes", { count: site.count })}</Badge>
                    {can("nodes.write") && site.name ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => openEditor(site)}
                        title={t("sites.editCoordinates")}
                        aria-label={t("sites.editCoordinates")}
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
        </>
      )}

      <Dialog open={editingSite !== null} onOpenChange={(open) => { if (!open) setEditingSite(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("sites.editCoordinatesTitle", { site: editingSite?.name ?? "" })}</DialogTitle>
            <DialogDescription>{t("sites.editCoordinatesDescription")}</DialogDescription>
          </DialogHeader>
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
          <DialogFooter>
            {editingSite?.latitude != null ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => editingSite?.name && saveCoordinates.mutate({ site: editingSite.name, value: null })}
                disabled={saveCoordinates.isPending}
              >
                {t("sites.clearCoordinates")}
              </Button>
            ) : null}
            <Button type="button" variant="outline" onClick={() => setEditingSite(null)} disabled={saveCoordinates.isPending}>
              {t("common.cancel")}
            </Button>
            <Button
              type="button"
              onClick={() => editingSite?.name && saveCoordinates.mutate({ site: editingSite.name, value: coordinates.trim() })}
              disabled={saveCoordinates.isPending || !coordinates.trim()}
            >
              {saveCoordinates.isPending ? <Spinner /> : null}
              {t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
