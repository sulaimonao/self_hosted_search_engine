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
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium">{job.description ?? job.jobId}</p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mt-1">
                    <span className={cn("flex items-center gap-1", meta.tone)}>
                      {meta.icon}
                      {meta.label}
                    </span>
                    {typeof job.etaSeconds === "number" && job.state === "running" && (
                      <Badge variant="outline">eta {Math.max(job.etaSeconds, 1)}s</Badge>
                    )}
                    <span>Updated {new Date(job.lastUpdated).toLocaleTimeString()}</span>
                  </div>
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
