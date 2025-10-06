"use client";

import { AlertCircle, CheckCircle2, Clock, PauseCircle, PlayCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import type { JobStatusSummary } from "@/lib/types";

interface JobStatusProps {
  jobs: JobStatusSummary[];
}

const STATUS_META: Record<JobStatusSummary["state"], { label: string; icon: ReactNode; tone: string }> = {
  idle: {
    label: "Idle",
    icon: <PauseCircle className="h-4 w-4" />,
    tone: "text-muted-foreground",
  },
  queued: {
    label: "Queued",
    icon: <Clock className="h-4 w-4" />,
    tone: "text-amber-500",
  },
  running: {
    label: "Running",
    icon: <PlayCircle className="h-4 w-4" />,
    tone: "text-sky-500",
  },
  done: {
    label: "Done",
    icon: <CheckCircle2 className="h-4 w-4" />,
    tone: "text-emerald-500",
  },
  error: {
    label: "Error",
    icon: <AlertCircle className="h-4 w-4" />,
    tone: "text-destructive",
  },
};

export function JobStatus({ jobs }: JobStatusProps) {
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Job status</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {jobs.length === 0 && (
          <p className="text-xs text-muted-foreground">No active jobs.</p>
        )}
        {jobs.map((job) => {
          const meta = STATUS_META[job.state];
          return (
            <div key={job.jobId} className="rounded border px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-sm font-medium">{job.description ?? job.jobId}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className={cn("flex items-center gap-1", meta.tone)}>
                      {meta.icon}
                      {meta.label}
                    </span>
                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                      {job.phase}
                    </Badge>
                    {typeof job.etaSeconds === "number" && job.state === "running" && job.etaSeconds > 0 && (
                      <Badge variant="outline">eta {formatEta(job.etaSeconds)}</Badge>
                    )}
                    <span>Updated {new Date(job.lastUpdated).toLocaleTimeString()}</span>
                  </div>
                  <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                    {renderStat("Fetched", job.stats.pagesFetched)}
                    {renderStat("Docs", job.stats.docsIndexed)}
                    {renderStat("Normalized", job.stats.normalizedDocs)}
                    {renderStat("Embedded", job.stats.embedded)}
                    {renderStat("Skipped", job.stats.skipped)}
                  </div>
                  {job.message && <p className="text-xs text-muted-foreground">{job.message}</p>}
                </div>
                {job.error && (
                  <Badge variant="destructive" className="text-[11px]">
                    {job.error}
                  </Badge>
                )}
              </div>
              <Progress value={job.progress} className="mt-2" />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function renderStat(label: string, value: number) {
  return (
    <span>
      <span className="font-medium text-foreground">{value}</span> {label}
    </span>
  );
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds)) return "--";
  const clamped = Math.max(0, Math.round(seconds));
  if (clamped < 60) {
    return `${clamped}s`;
  }
  const mins = Math.floor(clamped / 60);
  const secs = clamped % 60;
  return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}
