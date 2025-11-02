"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { AlertTriangle, CheckCircle, Loader2 } from "lucide-react";
import Link from "next/link";

import { Card } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { fetchHealth, type HealthSnapshot } from "@/lib/configClient";

function statusVariant(status?: string): string {
  switch (status) {
    case "ok":
      return "bg-emerald-500/10 text-emerald-700 border-emerald-500/40";
    case "degraded":
      return "bg-amber-500/10 text-amber-700 border-amber-500/40";
    case "error":
      return "bg-destructive/10 text-destructive border-destructive/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
}

function statusIcon(status?: string) {
  switch (status) {
    case "ok":
      return <CheckCircle className="h-4 w-4" />;
    case "degraded":
      return <AlertTriangle className="h-4 w-4" />;
    case "error":
      return <AlertTriangle className="h-4 w-4" />;
    default:
      return <Loader2 className="h-4 w-4 animate-spin" />;
  }
}

function formatComponentName(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function describeComponent(status: string | undefined, detail: Record<string, unknown>): string {
  if (!status || status === "ok") {
    return "Healthy";
  }
  if (status === "degraded") {
    if (Array.isArray(detail?.missing_families) && detail.missing_families.length > 0) {
      return `Missing ${detail.missing_families.join(", ")}`;
    }
    return "Attention required";
  }
  return "Unavailable";
}

export function StatusRibbon() {
  const { data, error } = useSWR<HealthSnapshot>("runtime-health", fetchHealth, {
    refreshInterval: 15000,
    revalidateOnFocus: true,
  });

  const overallStatus = error ? "error" : data?.status ?? "loading";
  const description = useMemo(() => {
    if (error) {
      return error instanceof Error ? error.message : "Failed to fetch health";
    }
    if (!data) {
      return "Checking systems…";
    }
    switch (data.status) {
      case "ok":
        return "All systems nominal";
      case "degraded":
        return "Some features need attention";
      case "error":
        return "Service disruption detected";
      default:
        return "Gathering telemetry";
    }
  }, [data, error]);

  const components = data?.components ?? {};

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 max-w-md">
      <Popover>
        <PopoverTrigger className="pointer-events-auto w-full text-left">
          <Card className={cn("flex items-center gap-3 px-4 py-2 shadow-lg", statusVariant(overallStatus))}>
            <span className="shrink-0">{statusIcon(overallStatus)}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold uppercase tracking-wide">Status</p>
              <p className="truncate text-sm font-medium">{description}</p>
            </div>
            <Link
              href="/control-center"
              className="pointer-events-auto rounded border border-current/20 px-2 py-1 text-[11px] font-semibold uppercase"
            >
              Control Center
            </Link>
          </Card>
        </PopoverTrigger>
        <PopoverContent className="w-72 text-sm" align="end">
          <div className="space-y-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Components</p>
              <ul className="mt-2 space-y-2">
                {Object.entries(components).map(([name, component]) => (
                  <li key={name} className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium">{formatComponentName(name)}</p>
                      <p className="text-xs text-muted-foreground">
                        {describeComponent(component.status, component.detail ?? {})}
                      </p>
                    </div>
                    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase", statusVariant(component.status))}>
                      {component.status ?? "unknown"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded border border-dashed p-2 text-xs text-muted-foreground">
              Status data captured {data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : "recently"}.
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

export default StatusRibbon;
