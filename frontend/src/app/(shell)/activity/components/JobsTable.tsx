"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent className="overflow-auto">
        {isLoading && <Skeleton className="h-32 w-full" />}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && (!jobs || jobs.length === 0) && (
          <p className="text-sm text-muted-foreground">No jobs found for the selected filters.</p>
        )}
        {!!jobs?.length && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground">
                <th className="py-2">Job</th>
                <th className="py-2">Type</th>
                <th className="py-2">Status</th>
                <th className="py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.id}
                  className={`cursor-pointer border-t transition ${selectedJobId === job.id ? "bg-primary/5" : "hover:bg-muted/40"}`}
                  onClick={() => onSelectJob?.(job.id)}
                  aria-selected={selectedJobId === job.id}
                >
                  <td className="py-2 font-mono text-xs">#{job.id}</td>
                  <td className="py-2">{job.type}</td>
                  <td className="py-2 capitalize">{job.status}</td>
                  <td className="py-2">{new Date(job.updated_at ?? job.created_at ?? Date.now()).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
