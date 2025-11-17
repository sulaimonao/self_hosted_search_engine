"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatThread } from "@/lib/useChatThread";
import { useTasksByThread } from "@/lib/backend/hooks";
import { TaskItem } from "@/components/ai/TaskItem";

export function TaskList() {
  const { currentThreadId } = useChatThread();
  const { data, isLoading, error } = useTasksByThread(currentThreadId);

  if (!currentThreadId) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border bg-background p-6 text-sm text-muted-foreground">
        Link a tab or open a session to view its tasks.
      </div>
    );
  }

  if (isLoading) {
    return (
      <ScrollArea className="flex-1 rounded-xl border bg-background p-3">
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      </ScrollArea>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border bg-background p-4 text-sm text-destructive">
        {error.message}
      </div>
    );
  }

  const tasks = data?.items ?? [];

  if (!tasks.length) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-xl border bg-background p-6 text-sm text-muted-foreground">
        No tasks linked to this thread yet.
      </div>
    );
  }

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
