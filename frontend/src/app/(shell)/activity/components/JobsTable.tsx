"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { JobRecord } from "@/lib/backend/types";

interface JobsTableProps {
  jobs?: JobRecord[];
  isLoading?: boolean;
  error?: string | null;
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
  onRetry?: () => void;
}

export function JobsTable({ jobs, isLoading, error, selectedJobId, onSelectJob, onRetry }: JobsTableProps) {
  const rowClasses =
    "flex w-full items-center justify-between gap-3 rounded-xs border border-transparent px-3 py-2 text-left text-sm transition-colors duration-fast hover:border-border-subtle hover:bg-app-card-hover cursor-pointer";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent className="overflow-auto">
        {isLoading && <Skeleton className="h-32 w-full" />}
        {error && (
          <div className="space-y-2 rounded-md border border-state-danger/40 bg-state-danger/10 p-3 text-sm text-state-danger">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && (!jobs || jobs.length === 0) && (
          <p className="text-sm text-fg-muted">No jobs found for the selected filters.</p>
        )}
        {!!jobs?.length && (
          <div className="space-y-2">
            {jobs.map((job) => {
              const selected = selectedJobId === job.id;
              return (
                <button
                  key={job.id}
                  type="button"
                  className={cn(rowClasses, selected ? "border-accent bg-accent-soft text-fg" : "cursor-pointer")}
                  onClick={() => onSelectJob?.(job.id)}
                >
                  <div className="flex w-full items-center gap-4 text-left">
                    <span className="font-mono text-xs text-fg-muted">#{job.id}</span>
                    <span className="text-sm text-fg">{job.type}</span>
                    <span className="text-xs uppercase tracking-wide text-fg-muted">{job.status}</span>
                    <span className="ml-auto text-xs text-fg-muted">
                      {new Date(job.updated_at ?? job.created_at ?? Date.now()).toLocaleString()}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
