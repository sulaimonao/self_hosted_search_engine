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
  const createdAt = task.created_at ? new Date(task.created_at).toLocaleString() : null;

  return (
    <div className="space-y-2 rounded-xl border border-border-subtle bg-app-card p-3">
      <div className="flex items-center justify-between text-sm">
        <p className="font-semibold text-fg">{task.title}</p>
        <Badge variant={badgeVariant}>{statusCopy}</Badge>
      </div>
      {task.description ? <p className="text-sm text-fg-muted whitespace-pre-line">{task.description}</p> : null}
      {createdAt && <p className="text-[11px] uppercase tracking-wide text-fg-muted">Created {createdAt}</p>}
    </div>
  );
}
