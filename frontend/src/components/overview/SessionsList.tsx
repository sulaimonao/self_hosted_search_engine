"use client";

import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { ThreadRecord } from "@/lib/backend/types";

interface SessionsListProps {
  threads?: ThreadRecord[];
  isLoading?: boolean;
  error?: string | null;
  onSelectThread?: (threadId: string) => void;
  onRetry?: () => void;
}

export function SessionsList({ threads, isLoading, error, onSelectThread, onRetry }: SessionsListProps) {
  const items = useMemo(() => threads ?? [], [threads]);
  const rowClasses =
    "flex w-full items-center justify-between gap-3 rounded-xs border border-transparent px-3 py-2 text-left transition-colors duration-fast hover:border-border-subtle hover:bg-app-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent cursor-pointer";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-fg">
        {isLoading && Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-16 w-full" />)}
        {error && (
          <div className="space-y-2 rounded-md border border-state-danger/40 bg-state-danger/10 p-3 text-state-danger">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && !items.length && <p className="text-fg-muted">No threads yet.</p>}
        {items.map((session) => (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelectThread?.(session.id)}
            className={rowClasses}
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-fg">{session.title || "Untitled thread"}</p>
              <p className="text-xs text-fg-muted">
                {session.updated_at ? new Date(session.updated_at).toLocaleString() : ""} · Origin: {session.origin ?? "unknown"}
              </p>
            </div>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
