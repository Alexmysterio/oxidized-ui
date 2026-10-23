import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { LogLine } from "@/types/api";

export type StreamStatus = "connecting" | "connected" | "disconnected" | "paused";

export function useLogStream({
  level,
  query,
  tail,
  paused,
  maxLines = 3000,
}: {
  level: string;
  query: string;
  tail: number;
  paused: boolean;
  maxLines?: number;
}) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [status, setStatus] = useState<StreamStatus>(paused ? "paused" : "connecting");
  const [streamError, setStreamError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (paused) {
      setStatus("paused");
      sourceRef.current?.close();
      sourceRef.current = null;
      return;
    }
    setLines([]);
    setStreamError(null);
    setStatus("connecting");
    const source = new EventSource(
      api.logsStreamUrl({
        tail,
        level: level && level !== "__all__" ? level : undefined,
        q: query || undefined,
      }),
    );
    sourceRef.current = source;
    source.addEventListener("ready", () => {
      // Docker replays the tail on every reconnect; replace the buffer so a
      // transient disconnect does not duplicate the visible history.
      setLines([]);
      setStreamError(null);
      setStatus("connected");
    });
    source.addEventListener("log", (event) => {
      if (!(event instanceof MessageEvent)) return;
      try {
        const line = JSON.parse(event.data) as LogLine;
        setLines((current) => {
          const next = [...current, line];
          return next.length > maxLines ? next.slice(next.length - maxLines) : next;
        });
      } catch {
        // Ignore malformed stream events.
      }
    });
    source.addEventListener("error", (event) => {
      if (event instanceof MessageEvent) {
        try {
          const payload = JSON.parse(event.data) as { code?: string };
          setStreamError(payload.code ?? "logs.stream_failed");
        } catch {
          setStreamError("logs.stream_failed");
        }
      }
      setStatus("disconnected");
    });
    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [paused, level, query, tail, maxLines]);

  return {
    lines,
    status,
    streamError,
    clear: () => setLines([]),
  };
}
