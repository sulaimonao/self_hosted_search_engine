import { ScrollArea } from "@/components/ui/scroll-area";
import { TaskItem } from "@/components/ai/TaskItem";

const tasks = [
  {
    id: "triage",
    title: "Triage crawling issues",
    status: "running" as const,
    summary: "Review jobs with high error counts and suggest fixes.",
  },
  {
    id: "summaries",
    title: "Generate daily digest",
    status: "ready" as const,
    summary: "Compile summaries for documents captured today.",
  },
  {
    id: "repo",
    title: "Apply repo fix",
    status: "blocked" as const,
    summary: "Waiting for user approval to apply patch.",
  },
];

export function TaskList() {
  return (
    <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
      <div className="space-y-3">
        {tasks.map((task) => (
          <TaskItem key={task.id} task={task} />
        ))}
      </div>
    </ScrollArea>
  );
}
