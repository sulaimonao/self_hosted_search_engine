import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const memories = [
  { id: "m1", title: "Browser session", detail: "Captured from electron://tab-1" },
  { id: "m2", title: "Memory", detail: "User asked about privacy policies." },
  { id: "m3", title: "Document", detail: "Design doc: HydraFlow tasks" },
];

export function ContextPeek() {
  return (
    <div className="flex-1 space-y-3 overflow-y-auto">
      {memories.map((memory) => (
        <Card key={memory.id}>
          <CardHeader>
            <CardTitle className="text-sm">{memory.title}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">{memory.detail}</CardContent>
        </Card>
      ))}
    </div>
  );
}
