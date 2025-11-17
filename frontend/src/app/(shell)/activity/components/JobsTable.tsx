"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobRecord } from "@/lib/backend/types";

interface JobsTableProps {
  jobs?: JobRecord[];
  isLoading?: boolean;
  error?: string | null;
  selectedJobId?: string | null;
  onSelectJob?: (jobId: string) => void;
}

export function JobsTable({ jobs, isLoading, error, selectedJobId, onSelectJob }: JobsTableProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent className="overflow-auto">
        {isLoading && <Skeleton className="h-32 w-full" />}
        {!isLoading && error && <p className="text-sm text-destructive">{error}</p>}
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
                  className={`border-t ${selectedJobId === job.id ? "bg-muted/40" : ""}`}
                  onClick={() => onSelectJob?.(job.id)}
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
