"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBrowserTabs, useMemories } from "@/lib/backend/hooks";
import { inferResearchSessionFromThread } from "@/lib/researchSession";
import { useChatThread } from "@/lib/useChatThread";

export function ContextPeek() {
  const { currentThreadId, currentThread } = useChatThread();
  const tabsQuery = useBrowserTabs();
  const memoriesQuery = useMemories(currentThreadId);
  const session = inferResearchSessionFromThread(currentThread);

  const linkedTab = tabsQuery.data?.items.find((tab) => tab.thread_id === currentThreadId);

  return (
    <div className="flex-1 space-y-3 overflow-y-auto">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Session</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-fg">
          {session ? (
            <>
              <p className="font-medium">{session.topic ?? currentThread?.title ?? `Thread ${session.threadId}`}</p>
              <p className="text-xs text-fg-muted">Started {new Date(session.createdAt).toLocaleString()}</p>
            </>
          ) : (
            <p className="text-sm text-fg-muted">Link a browser thread to view its session metadata.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Current tab</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          {tabsQuery.isLoading && <Skeleton className="h-14 w-full" />}
          {tabsQuery.error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              <p>{tabsQuery.error.message}</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => tabsQuery.refetch()}>
                Retry
              </Button>
            </div>
          )}
          {!tabsQuery.isLoading && !tabsQuery.error && linkedTab && (
            <div>
              <p className="font-medium text-foreground">{linkedTab.current_title ?? "Untitled"}</p>
              <p className="truncate text-xs">{linkedTab.current_url ?? "Unknown URL"}</p>
            </div>
          )}
          {!tabsQuery.isLoading && !tabsQuery.error && !linkedTab && <p>No tab linked to this thread.</p>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Relevant memories</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          {!currentThreadId && <p>Memories load once a thread is active.</p>}
          {currentThreadId && memoriesQuery.isLoading && <Skeleton className="h-16 w-full" />}
          {currentThreadId && memoriesQuery.error && (
            <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              <p>{memoriesQuery.error.message}</p>
              <Button variant="outline" size="sm" onClick={() => memoriesQuery.refetch()}>
                Retry
              </Button>
            </div>
          )}
          {currentThreadId && !memoriesQuery.isLoading && !memoriesQuery.error && (memoriesQuery.data?.items.length ?? 0) === 0 && (
            <p>No session notes captured yet.</p>
          )}
          {memoriesQuery.data?.items.map((memory) => (
            <div key={memory.id} className="rounded-md border border-border-subtle bg-app-card-subtle p-2">
              <p className="font-medium text-foreground">{memory.key ?? memory.scope}</p>
              <p className="text-xs text-fg-muted whitespace-pre-wrap">{memory.value}</p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
