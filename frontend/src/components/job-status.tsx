<<<<<<< ours
<<<<<<< ours
export function JobStatus() {
  return (
    <div className="p-2 border-t">
      <p>Job Status: Idle</p>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { JobSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

interface JobStatusProps {
  jobs: JobSummary[];
  activeJobId?: string;
  onSelect?: (jobId: string) => void;
}

const statusToBadge: Record<JobSummary["status"], "warning" | "success" | "secondary" | "destructive"> = {
  queued: "secondary",
  running: "warning",
  completed: "success",
  failed: "destructive",
};

export function JobStatus({ jobs, activeJobId, onSelect }: JobStatusProps) {
  const totals = useMemo(() => {
    return jobs.reduce(
      (acc, job) => {
        acc[job.status] = (acc[job.status] ?? 0) + 1;
        return acc;
      },
      {} as Record<JobSummary["status"], number>,
    );
  }, [jobs]);

  return (
    <Card className="border-muted-foreground/30">
      <CardHeader className="pb-4">
        <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Job Status
        </CardTitle>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          {Object.entries(totals).map(([status, count]) => (
            <span key={status} className="flex items-center gap-1">
              <Badge variant={statusToBadge[status as JobSummary["status"]]}>{status}</Badge>
              <span>{count}</span>
            </span>
          ))}
          {jobs.length === 0 && <span>No jobs yet</span>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {jobs.slice(0, 5).map((job) => (
          <button
            key={job.id}
            onClick={() => onSelect?.(job.id)}
            className={cn(
              "flex w-full flex-col items-start rounded-md border border-transparent bg-muted/40 p-2 text-left transition hover:border-primary/50 hover:bg-muted",
              activeJobId === job.id && "border-primary bg-primary/10",
            )}
          >
            <div className="flex w-full items-center justify-between text-xs">
              <span className="font-medium uppercase text-muted-foreground">{job.id}</span>
              <Badge variant={statusToBadge[job.status]}>{job.status}</Badge>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.round(job.progress * 100)}%` }} />
            </div>
            {job.lastEvent && <p className="mt-1 text-xs text-muted-foreground">{job.lastEvent.message}</p>}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
