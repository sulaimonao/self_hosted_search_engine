"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import { fetchHealth, type HealthSnapshot } from "@/lib/configClient";

const COMPONENTS: Array<{ key: keyof HealthSnapshot["components"]; label: string }> = [
  { key: "crawler", label: "Crawler" },
  { key: "desktop", label: "Desktop" },
  { key: "index", label: "Index" },
  { key: "llm", label: "LLM" },
];

const POLL_INTERVAL_MS = 10000;

function statusClasses(status?: string): string {
  switch (status) {
    case "ok":
    case "running":
      return "bg-state-success";
    case "degraded":
    case "idle":
      return "bg-state-warning";
    case "error":
    case "unavailable":
      return "bg-state-danger";
    default:
      return "bg-muted-foreground/60";
  }
}

function statusLabel(status?: string): string {
  if (!status) return "unknown";
  return status;
}

export function StatusBar() {
  const [snapshot, setSnapshot] = useState<HealthSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await fetchHealth();
        if (!cancelled) {
          setSnapshot(payload);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Health fetch failed";
          setError(message);
        }
      }
    };
    void load();
    timerRef.current = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  const timestamp = useMemo(() => {
    if (snapshot?.timestamp) {
      return new Date(snapshot.timestamp).toLocaleTimeString();
    }
    return "—";
  }, [snapshot?.timestamp]);

  const components = snapshot?.components ?? {};

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40">
      <div className="pointer-events-auto border-t border-border/80 bg-background/95 shadow-[0_-8px_20px_-12px_rgba(0,0,0,0.45)] backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-2 text-xs sm:text-sm">
          <Link href="/browser" className="font-semibold text-primary underline-offset-4 hover:underline">
            Back to Browser
          </Link>
          <div className="flex flex-1 items-center justify-center gap-4 text-muted-foreground transition hover:text-foreground">
            {COMPONENTS.map(({ key, label }) => {
              const component = components[key];
              const status = statusLabel(component?.status);
              return (
                <span key={key} className="flex items-center gap-1 text-[11px] uppercase tracking-wide sm:text-xs">
                  <span className={cn("h-2 w-2 rounded-full", statusClasses(component?.status))} />
                  {label}: {status}
                </span>
              );
            })}
          </div>
          <Link href="/control-center" className="text-muted-foreground hover:text-foreground">
            {error ? "health unavailable" : timestamp}
          </Link>
        </div>
      </div>
    </div>
  );
}

export default StatusBar;
