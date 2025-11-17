import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export type ActivityItem = {
  id: string;
  title: string;
  timestamp: string;
  status: string;
};

export function ActivityTimeline({ items }: { items: ActivityItem[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-4 text-sm">
          {items.map((item) => (
            <li key={item.id} className="flex items-center gap-3">
              <span className="size-2 rounded-full bg-primary" aria-hidden />
              <div>
                <p className="font-medium">{item.title}</p>
                <p className="text-xs text-muted-foreground">{item.timestamp} · {item.status}</p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
