import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { RepoChange } from "@/app/(shell)/repo/components/RepoChangesTable";

export function RepoChangeDetail({ change }: { change?: RepoChange }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change detail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        {!change && <p>Select a change to inspect the AI proposal, patches, and linked jobs.</p>}
        {change && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <p className="text-base font-semibold text-foreground">{change.title}</p>
              <Badge variant="outline">{change.status}</Badge>
            </div>
            <p>{change.summary ?? "AI-generated plan details will appear here."}</p>
            {change.jobId && <p className="text-xs text-foreground">Linked job: {change.jobId}</p>}
            <p className="text-xs text-muted-foreground">Activity panel opens the job drawer for deeper inspection.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
