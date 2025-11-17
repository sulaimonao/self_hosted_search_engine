import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function RepoChangeDetail() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change detail</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Select a change to inspect the AI proposal, patches, and linked jobs.
      </CardContent>
    </Card>
  );
}
