import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function RepoStatusCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repo health</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Checks, patch proposals, and AI guidance appear here once repos are synced.
      </CardContent>
    </Card>
  );
}
