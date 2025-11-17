import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobRecord } from "@/lib/backend/types";

interface BundleJobsSummaryProps {
  jobs?: JobRecord[];
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function BundleJobsSummary({ jobs, isLoading, error, onRetry }: BundleJobsSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Bundle jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && (!jobs || jobs.length === 0) && <p className="text-muted-foreground">No bundle jobs yet.</p>}
        {jobs?.map((job) => (
          <div key={job.id} className="rounded-lg border p-2">
            <p className="font-medium text-foreground">{job.type}</p>
            <p className="text-xs text-muted-foreground">
              #{job.id} · {job.status} · {new Date(job.updated_at ?? job.created_at ?? Date.now()).toLocaleString()}
            </p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
