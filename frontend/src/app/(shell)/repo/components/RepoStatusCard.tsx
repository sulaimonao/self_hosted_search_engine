import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RepoStatusSummary } from "@/lib/backend/types";
import { Skeleton } from "@/components/ui/skeleton";

interface RepoStatusCardProps {
  status?: RepoStatusSummary;
  isLoading?: boolean;
}

export function RepoStatusCard({ status, isLoading }: RepoStatusCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repo health</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground space-y-2">
        {isLoading && <Skeleton className="h-20 w-full" />}
        {!isLoading && !status && <p>Select a repository to view its git status.</p>}
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
