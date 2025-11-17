import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type Session = {
  id: string;
  title: string;
  timestamp: string;
  summary: string;
};

export function SessionsList({ sessions }: { sessions: Session[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {sessions.map((session) => (
          <div key={session.id} className="border-l-2 border-primary/30 pl-4">
            <p className="text-sm font-medium">{session.title}</p>
            <p className="text-xs text-muted-foreground">{session.timestamp}</p>
            <p className="text-sm text-muted-foreground">{session.summary}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
