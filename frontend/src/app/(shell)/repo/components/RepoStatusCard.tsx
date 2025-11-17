import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { RepoStatusSummary } from "@/lib/backend/types";

interface RepoStatusCardProps {
  status?: RepoStatusSummary;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function RepoStatusCard({ status, isLoading, error, onRetry }: RepoStatusCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repo health</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm text-muted-foreground">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && !status && <p>Select a repository to view its git status.</p>}
        {status && (
          <div className="space-y-2">
            <p>Branch: {status.branch ?? "unknown"}</p>
            <p>Dirty: {status.dirty ? "Yes" : "No"}</p>
            <p>Ahead/behind: {status.ahead ?? 0}/{status.behind ?? 0}</p>
            {status.changes?.length ? (
              <div>
                <p className="text-xs uppercase">Recent changes</p>
                <ul className="text-xs">
                  {status.changes.slice(0, 5).map((change) => (
                    <li key={change}>{change}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
