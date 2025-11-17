import { Badge } from "@/components/ui/badge";

type Task = {
  id: string;
  title: string;
  status: "ready" | "running" | "blocked";
  summary: string;
};

export function TaskItem({ task }: { task: Task }) {
  const statusCopy = {
    ready: "Ready",
    running: "In progress",
    blocked: "Blocked",
  }[task.status];

  const badgeVariant = task.status === "running" ? "default" : task.status === "blocked" ? "destructive" : "secondary";

  return (
    <div className="space-y-1 rounded-xl border bg-card/70 p-3">
      <div className="flex items-center justify-between text-sm">
        <p className="font-semibold">{task.title}</p>
        <Badge variant={badgeVariant}>{statusCopy}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{task.summary}</p>
    </div>
  );
}
