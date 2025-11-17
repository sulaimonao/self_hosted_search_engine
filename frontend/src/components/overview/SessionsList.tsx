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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {isLoading && Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-16 w-full" />)}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && !items.length && <p className="text-muted-foreground">No threads yet.</p>}
        {items.map((session) => (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelectThread?.(session.id)}
            className="flex h-16 w-full items-center justify-between rounded-xl border px-3 text-left transition hover:border-primary/60"
          >
            <div>
              <p className="text-sm font-medium">{session.title || "Untitled thread"}</p>
              <p className="text-xs text-muted-foreground">
                {session.updated_at ? new Date(session.updated_at).toLocaleString() : ""} · Origin: {session.origin ?? "unknown"}
              </p>
            </div>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
