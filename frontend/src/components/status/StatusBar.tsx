"use client";

import Link from "next/link";
import useSWR from "swr";

import { cn } from "@/lib/utils";
import { fetchHealth, type HealthSnapshot } from "@/lib/configClient";

const COMPONENTS: Array<{ key: string; label: string }> = [
  { key: "crawler", label: "Crawler" },
  { key: "desktop", label: "Desktop" },
  { key: "index", label: "Index" },
  { key: "llm", label: "LLM" },
];

function statusClasses(status?: string): string {
  switch (status) {
    case "ok":
      return "bg-emerald-500";
    case "degraded":
      return "bg-amber-500";
    case "error":
    case "unavailable":
      return "bg-destructive";
    default:
      return "bg-muted-foreground/60";
  }
}

function statusLabel(status?: string): string {
  if (!status) return "unknown";
  return status;
}

export function StatusBar() {
  const { data, error } = useSWR<HealthSnapshot>("runtime-health", fetchHealth, {
    refreshInterval: 15000,
    revalidateOnFocus: true,
  });
  const timestamp = data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : "—";
  const components = data?.components ?? {};

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40">
      <div className="pointer-events-auto border-t border-border/80 bg-background/95 shadow-[0_-8px_20px_-12px_rgba(0,0,0,0.45)] backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-2 text-xs sm:text-sm">
          <Link href="/browser" className="font-semibold text-primary underline-offset-4 hover:underline">
            Back to Browser
          </Link>
          <Link
            href="/control-center"
            className="flex flex-1 items-center justify-center gap-4 text-muted-foreground transition hover:text-foreground"
          >
            {COMPONENTS.map(({ key, label }) => {
              const status = statusLabel(components[key]?.status);
              return (
                <span key={key} className="flex items-center gap-1 text-[11px] uppercase tracking-wide sm:text-xs">
                  <span className={cn("h-2 w-2 rounded-full", statusClasses(components[key]?.status))} />
                  {label}: {status}
                </span>
              );
            })}
          </Link>
          <Link href="/control-center" className="text-muted-foreground hover:text-foreground">
            {error ? "health unavailable" : timestamp}
          </Link>
        </div>
      </div>
    </div>
  );
}

export default StatusBar;
