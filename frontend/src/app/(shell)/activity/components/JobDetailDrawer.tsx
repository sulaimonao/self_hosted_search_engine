import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function JobDetailDrawer() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Job detail</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Select a job to inspect its HydraFlow events and AI notes.
      </CardContent>
    </Card>
  );
}
