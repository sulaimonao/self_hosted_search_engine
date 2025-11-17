"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBrowserTabs, useMemories } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";

export function ContextPeek() {
  const { currentThreadId } = useChatThread();
  const { data: tabs } = useBrowserTabs();
  const { data: memories, isLoading, error } = useMemories(currentThreadId);

  const linkedTab = tabs?.items.find((tab) => tab.thread_id === currentThreadId);

  return (
    <div className="flex-1 space-y-3 overflow-y-auto">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Current tab</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {linkedTab ? (
            <div>
              <p className="font-medium text-foreground">{linkedTab.current_title ?? "Untitled"}</p>
              <p className="truncate text-xs">{linkedTab.current_url ?? "Unknown URL"}</p>
            </div>
          ) : (
            <p>No tab linked to this thread.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Relevant memories</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          {!currentThreadId && <p>Memories load once a thread is active.</p>}
          {currentThreadId && isLoading && <Skeleton className="h-16 w-full" />}
          {currentThreadId && error && <p className="text-destructive">{error.message}</p>}
          {currentThreadId && !isLoading && !error && (memories?.items.length ?? 0) === 0 && (
            <p>No memories retrieved.</p>
          )}
          {memories?.items.map((memory) => (
            <div key={memory.id}>
              <p className="font-medium text-foreground">{memory.key ?? memory.scope}</p>
              <p className="text-xs">{memory.value}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
