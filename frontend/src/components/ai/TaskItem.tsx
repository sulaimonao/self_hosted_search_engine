import { Badge } from "@/components/ui/badge";
import type { TaskRecord } from "@/lib/backend/types";

export function TaskItem({ task }: { task: TaskRecord }) {
  const normalizedStatus = (task.status || "").toLowerCase();
  const statusCopy = normalizedStatus ? normalizedStatus.replace(/_/g, " ") : "unknown";
  const badgeVariant =
    normalizedStatus === "running"
      ? "default"
      : normalizedStatus === "failed" || normalizedStatus === "error"
        ? "destructive"
        : "secondary";

  return (
    <div className="space-y-1 rounded-xl border bg-card/70 p-3">
      <div className="flex items-center justify-between text-sm">
        <p className="font-semibold">{task.title}</p>
        <Badge variant={badgeVariant}>{statusCopy}</Badge>
      </div>
      {task.description ? <p className="text-sm text-muted-foreground">{task.description}</p> : null}
    </div>
  );
}
