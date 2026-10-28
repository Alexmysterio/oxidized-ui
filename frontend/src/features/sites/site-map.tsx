import "leaflet/dist/leaflet.css";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Link } from "react-router-dom";

import type { SiteGroup } from "@/types/api";

type Point = [number, number];
type LocatedSite = SiteGroup & { latitude: number; longitude: number };

const STATUS_COLOR: Record<string, string> = {
  ok: "#22a06b",
  failed: "#e05252",
  pending: "#d9a521",
  never: "#94a3b8",
};

const EMPTY_TILE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

function siteColor(site: SiteGroup): string {
  if (site.status.failed) return STATUS_COLOR.failed;
  if (site.status.pending) return STATUS_COLOR.pending;
  if (site.status.never) return STATUS_COLOR.never;
  return STATUS_COLOR.ok;
}

function siteRadius(count: number): number {
  return 8 + Math.min(9, Math.log2(count + 1) * 3);
}

function MapEffects({ points, signature }: { points: Point[]; signature: string }) {
  const map = useMap();

  useEffect(() => {
    const timer = window.setTimeout(() => {
      map.invalidateSize();
      if (points.length === 1) {
        map.setView(points[0], 11);
      } else if (points.length > 1) {
        map.fitBounds(points, { padding: [40, 40], maxZoom: 13 });
      }
    }, 120);
    return () => window.clearTimeout(timer);
    // `signature` changes only when the marker set changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, signature]);

  return null;
}

export function SiteMap({ sites, onBackup }: { sites: LocatedSite[]; onBackup?: (site: LocatedSite) => void }) {
  const { t } = useTranslation();
  const points = useMemo<Point[]>(
    () => sites.map((site) => [site.latitude, site.longitude]),
    [sites],
  );
  const signature = points.map((point) => point.join(",")).join("|");
  const center: Point = points[0] ?? [20, 0];
  const [tilesFailed, setTilesFailed] = useState(false);

  return (
    <>
      <MapContainer
        center={center}
        zoom={points.length === 1 ? 11 : 5}
        scrollWheelZoom={false}
        className="h-[22rem] w-full rounded-lg border"
        aria-label={t("sites.map")}
      >
        <TileLayer
          url="/api/map/tiles/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors'
          maxZoom={19}
          noWrap
          errorTileUrl={EMPTY_TILE}
          eventHandlers={{ tileerror: () => setTilesFailed(true) }}
        />
        <MapEffects points={points} signature={signature} />
        {sites.map((site) => (
          <CircleMarker
            key={site.name ?? "__none__"}
            center={[site.latitude, site.longitude]}
            radius={siteRadius(site.count)}
            pathOptions={{
              color: siteColor(site),
              fillColor: siteColor(site),
              fillOpacity: 0.85,
              weight: 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              {site.name ?? t("sites.noSite")} · {t("sites.nodes", { count: site.count })}
            </Tooltip>
            <Popup maxWidth={340}>
              <div className="space-y-1.5">
                <p className="font-semibold">{site.name ?? t("sites.noSite")}</p>
                <p className="text-[11px] text-muted-foreground">{t("sites.nodes", { count: site.count })}</p>
                <div className="max-h-52 space-y-0.5 overflow-y-auto">
                  {site.nodes.map((node) => (
                    <Link
                      key={node.id}
                      to={`/nodes/${node.id}`}
                      className="flex items-center justify-between gap-2 rounded px-1 py-0.5 text-[11px] hover:bg-accent"
                    >
                      <span className="truncate font-medium">{node.name}</span>
                      <span className="shrink-0 text-muted-foreground">{t(`nodeStatus.${node.status}`)}</span>
                    </Link>
                  ))}
                </div>
                {onBackup ? (
                  <button
                    type="button"
                    onClick={() => onBackup(site)}
                    className="mt-1 w-full rounded-md border border-border bg-card px-2 py-1 text-[11px] font-medium transition-colors hover:bg-accent"
                  >
                    {t("sites.backup")}
                  </button>
                ) : null}
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {tilesFailed ? <p className="text-[11px] text-destructive">{t("sites.mapUnavailable")}</p> : null}
    </>
  );
}
