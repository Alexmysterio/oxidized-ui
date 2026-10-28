import "leaflet/dist/leaflet.css";

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleMarker, MapContainer, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";
import { Link } from "react-router-dom";

import type { SiteNode } from "@/types/api";

type Point = [number, number];

const STATUS_COLOR: Record<string, string> = {
  ok: "#22a06b",
  failed: "#e05252",
  pending: "#d9a521",
  never: "#94a3b8",
};

const EMPTY_TILE =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

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

export function SiteMap({ nodes }: { nodes: (SiteNode & { latitude: number; longitude: number })[] }) {
  const { t } = useTranslation();
  const points = useMemo<Point[]>(
    () => nodes.map((node) => [node.latitude, node.longitude]),
    [nodes],
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
        {nodes.map((node) => (
          <CircleMarker
            key={node.id}
            center={[node.latitude, node.longitude]}
            radius={8}
            pathOptions={{
              color: STATUS_COLOR[node.status] ?? STATUS_COLOR.never,
              fillColor: STATUS_COLOR[node.status] ?? STATUS_COLOR.never,
              fillOpacity: 0.85,
              weight: 2,
            }}
          >
            <Tooltip direction="top" offset={[0, -8]}>
              {node.name}
            </Tooltip>
            <Popup>
              <div className="space-y-1 text-xs">
                <p className="font-semibold">{node.name}</p>
                <p className="font-mono text-[11px] text-muted-foreground">
                  {node.latitude.toFixed(5)}, {node.longitude.toFixed(5)}
                </p>
                <Link className="font-medium text-primary underline-offset-2 hover:underline" to={`/nodes/${node.id}`}>
                  {t("sites.openNode")}
                </Link>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {tilesFailed ? <p className="text-[11px] text-destructive">{t("sites.mapUnavailable")}</p> : null}
    </>
  );
}
