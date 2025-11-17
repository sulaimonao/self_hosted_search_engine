import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const changes = [
  { id: "c1", title: "Upgrade dependencies", status: "Proposed" },
  { id: "c2", title: "Improve telemetry", status: "Applied" },
];

export function RepoChangesTable() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Change log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {changes.map((change) => (
          <div key={change.id} className="rounded-lg border p-3">
            <p className="font-medium">{change.title}</p>
            <p className="text-xs text-muted-foreground">{change.status}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
