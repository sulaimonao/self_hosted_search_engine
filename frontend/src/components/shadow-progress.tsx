"use client";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { JobStatusSummary } from "@/lib/types";

interface ShadowProgressProps {
  job: JobStatusSummary;
}

function formatEta(seconds?: number) {
  if (!seconds || !Number.isFinite(seconds)) return "--";
  const clamped = Math.max(0, Math.round(seconds));
  if (clamped < 60) return `${clamped}s`;
  const minutes = Math.floor(clamped / 60);
  const remaining = clamped % 60;
  return `${minutes}m ${remaining.toString().padStart(2, "0")}s`;
}

export function ShadowProgress({ job }: ShadowProgressProps) {
  const percent = Math.max(0, Math.min(100, Math.round(job.progress)));
  return (
    <div className="bg-muted/40 px-3 py-2 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-foreground">{job.phase}</span>
          <Badge variant="outline">{percent}%</Badge>
          {typeof job.etaSeconds === "number" && job.etaSeconds > 0 && (
            <Badge variant="outline">eta {formatEta(job.etaSeconds)}</Badge>
          )}
          {typeof job.retries === "number" && job.retries > 0 && (
            <Badge variant="outline">retries {job.retries}</Badge>
          )}
        </div>
        <span className="text-muted-foreground">{new Date(job.lastUpdated).toLocaleTimeString()}</span>
      </div>
      <Progress value={percent} className="mt-2" />
      {job.message && (
        <p className="mt-2 text-[11px] text-muted-foreground">{job.message}</p>
      )}
    </div>
  );
}
