"use client";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatThread } from "@/lib/useChatThread";
import { useTasksByThread } from "@/lib/backend/hooks";
import { TaskItem } from "@/components/ai/TaskItem";

export function TaskList() {
  const { currentThreadId } = useChatThread();
  const { data, isLoading, error, refetch, isRefetching } = useTasksByThread(currentThreadId);

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
      <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-background p-6 text-center text-sm text-destructive">
        <p>{error.message}</p>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isRefetching}>
          Retry
        </Button>
      </div>
    );
  }

  const tasks = data?.items ?? [];

  if (!tasks.length) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-background p-6 text-center text-sm text-muted-foreground">
        <p className="text-base font-medium text-foreground">No tasks yet</p>
        <p>Create a task from this conversation to track follow-ups.</p>
        <Button variant="outline" size="sm" disabled>
          Create task from chat
        </Button>
        <p className="text-[11px] text-muted-foreground">Available once backend task APIs are linked.</p>
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
