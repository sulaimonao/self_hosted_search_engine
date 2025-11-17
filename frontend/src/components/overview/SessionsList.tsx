"use client";

import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { ThreadRecord } from "@/lib/backend/types";

interface SessionsListProps {
  threads?: ThreadRecord[];
  isLoading?: boolean;
  error?: string | null;
  onSelectThread?: (threadId: string) => void;
}

export function SessionsList({ threads, isLoading, error, onSelectThread }: SessionsListProps) {
  const items = useMemo(() => threads ?? [], [threads]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent sessions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {isLoading && Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-16 w-full" />)}
        {!isLoading && error && <p className="text-destructive">{error}</p>}
        {!isLoading && !error && !items.length && <p className="text-muted-foreground">No threads yet.</p>}
        {items.map((session) => (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelectThread?.(session.id)}
            className="w-full border-l-2 border-primary/30 pl-4 text-left transition hover:text-primary"
          >
            <p className="text-sm font-medium">{session.title || "Untitled thread"}</p>
            <p className="text-xs text-muted-foreground">
              {session.updated_at ? new Date(session.updated_at).toLocaleString() : ""}
            </p>
            <p className="text-xs text-muted-foreground">Origin: {session.origin ?? "unknown"}</p>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
