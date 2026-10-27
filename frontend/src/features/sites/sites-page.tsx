import { useQuery } from "@tanstack/react-query";
import { Map as MapIcon, MapPin, Network } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { NodeStatusBadge } from "@/components/shared/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { NodeStatus, SiteNode } from "@/types/api";

const statusColor: Record<string, string> = {
  ok: "#22a06b",
  failed: "#e05252",
  pending: "#d9a521",
  never: "#94a3b8",
};

function MapPlot({ nodes }: { nodes: (SiteNode & { latitude: number; longitude: number })[] }) {
  const bounds = useMemo(() => {
    const lats = nodes.map((node) => node.latitude);
    const lons = nodes.map((node) => node.longitude);
    return {
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
      minLon: Math.min(...lons),
      maxLon: Math.max(...lons),
    };
  }, [nodes]);
  const spanLat = Math.max(bounds.maxLat - bounds.minLat, 0.01);
  const spanLon = Math.max(bounds.maxLon - bounds.minLon, 0.01);
  return (
    <div className="relative h-72 w-full overflow-hidden rounded-lg border bg-muted/10">
      <svg viewBox="0 0 100 60" className="h-full w-full" preserveAspectRatio="none">
        {Array.from({ length: 6 }).map((_, index) => (
          <line key={`h-${index}`} x1="0" x2="100" y1={index * 12} y2={index * 12} stroke="currentColor" strokeWidth="0.1" className="text-border" />
        ))}
        {Array.from({ length: 10 }).map((_, index) => (
          <line key={`v-${index}`} y1="0" y2="60" x1={index * 11.1} x2={index * 11.1} stroke="currentColor" strokeWidth="0.1" className="text-border" />
        ))}
        {nodes.map((node) => {
          const x = ((node.longitude - bounds.minLon) / spanLon) * 92 + 4;
          const y = 56 - ((node.latitude - bounds.minLat) / spanLat) * 52;
          return (
            <g key={node.id}>
              <title>{`${node.name} (${node.latitude}, ${node.longitude})`}</title>
              <circle cx={x} cy={y} r="1.4" fill={statusColor[node.status] ?? statusColor.never} />
              <text x={x + 1.8} y={y + 1} fontSize="2" className="fill-foreground">
                {node.name}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function SitesPage() {
  const { t } = useTranslation();
  const [tag, setTag] = useState("Site");
  usePageTitle("nav.sites");

  const tagsQuery = useQuery({ queryKey: ["node-tags"], queryFn: api.nodeTags });
  const sitesQuery = useQuery({ queryKey: ["sites", tag], queryFn: () => api.sites(tag) });
  const tagKeys = Array.from(new Set(["Site", ...(tagsQuery.data?.items ?? []).map((item) => item.key)]));
  const sites = sitesQuery.data?.sites ?? [];
  const mapped = sites.flatMap((site) =>
    site.nodes.filter(
      (node): node is SiteNode & { latitude: number; longitude: number } =>
        typeof node.latitude === "number" && typeof node.longitude === "number",
    ),
  );

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
          {mapped.length ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{t("sites.map")}</CardTitle>
                <CardDescription>{t("sites.mapDescription")}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <MapPlot nodes={mapped} />
                <p className="text-[11px] text-muted-foreground">{t("sites.mapHelp")}</p>
              </CardContent>
            </Card>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sites.map((site) => (
              <Card key={site.name ?? "__none__"}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <MapPin className="h-4 w-4 text-primary" />
                    {site.name ?? t("sites.noSite")}
                    <Badge variant="outline" className="ml-auto">{t("sites.nodes", { count: site.count })}</Badge>
                  </CardTitle>
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
    </div>
  );
}
