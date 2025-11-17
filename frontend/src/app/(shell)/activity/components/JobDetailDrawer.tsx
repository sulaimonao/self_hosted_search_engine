"use client";

import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobRecord } from "@/lib/backend/types";

interface JobDetailDrawerProps {
  job?: JobRecord;
  isLoading?: boolean;
  error?: string | null;
  onOpenThread?: (threadId: string) => void;
  onOpenRepo?: () => void;
}

export function JobDetailDrawer({ job, isLoading, error, onOpenThread, onOpenRepo }: JobDetailDrawerProps) {
  const payloadPreview = useMemo(() => JSON.stringify(job?.payload ?? {}, null, 2), [job?.payload]);
  const resultPreview = useMemo(() => JSON.stringify(job?.result ?? {}, null, 2), [job?.result]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Job detail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        {isLoading && <Skeleton className="h-32 w-full" />}
        {error && <p className="text-destructive">{error}</p>}
        {!isLoading && !error && !job && <p>Select a job to inspect its payload and logs.</p>}
        {job && (
          <div className="space-y-3">
            <div>
              <p className="text-xs uppercase text-muted-foreground">Job</p>
              <p className="font-mono text-sm text-foreground">#{job.id}</p>
              <p className="text-xs">{job.type} · {job.status}</p>
            </div>
            {job.thread_id && (
              <Button size="sm" variant="secondary" onClick={() => onOpenThread?.(job.thread_id ?? "")}>Open thread</Button>
            )}
            <div>
              <p className="text-xs uppercase text-muted-foreground">Payload</p>
              <pre className="max-h-40 overflow-auto rounded-lg bg-muted/60 p-2 text-xs text-foreground">{payloadPreview}</pre>
            </div>
            <div>
              <p className="text-xs uppercase text-muted-foreground">Result</p>
              <pre className="max-h-40 overflow-auto rounded-lg bg-muted/60 p-2 text-xs text-foreground">{resultPreview}</pre>
            </div>
            {job.error && <p className="text-destructive">Error: {job.error}</p>}
            {job.type?.startsWith("repo_") && (
              <Button size="sm" variant="outline" onClick={onOpenRepo}>Open repo tools</Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
