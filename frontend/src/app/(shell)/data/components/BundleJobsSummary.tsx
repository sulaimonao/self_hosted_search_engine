import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { JobRecord } from "@/lib/backend/types";
import { Skeleton } from "@/components/ui/skeleton";

interface BundleJobsSummaryProps {
  jobs?: JobRecord[];
  isLoading?: boolean;
  error?: string | null;
}

export function BundleJobsSummary({ jobs, isLoading, error }: BundleJobsSummaryProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Bundle jobs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {!isLoading && error && <p className="text-destructive">{error}</p>}
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
