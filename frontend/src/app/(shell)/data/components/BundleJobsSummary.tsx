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
  const rowClasses =
    "flex items-center justify-between gap-3 rounded-xs border border-transparent px-3 py-2 transition-colors duration-fast hover:border-border-subtle hover:bg-app-card-hover";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bundle jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-fg">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {error && (
          <div className="space-y-2 rounded-md border border-state-danger/40 bg-state-danger/10 p-3 text-state-danger">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && (!jobs || jobs.length === 0) && <p className="text-fg-muted">No bundle jobs yet.</p>}
        {jobs?.map((job) => (
          <div key={job.id} className={rowClasses}>
            <div>
              <p className="text-sm font-medium text-fg">{job.type}</p>
              <p className="text-xs text-fg-muted">
              #{job.id} · {job.status} · {new Date(job.updated_at ?? job.created_at ?? Date.now()).toLocaleString()}
            </p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
