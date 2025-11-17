"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { JobRecord } from "@/lib/backend/types";

interface ActivityTimelineProps {
  items?: JobRecord[];
  isLoading?: boolean;
  error?: string | null;
  onSelectJob?: (jobId: string) => void;
  onRetry?: () => void;
}

export function ActivityTimeline({ items, isLoading, error, onSelectJob, onRetry }: ActivityTimelineProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading && Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-12 w-full" />)}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && (!items || items.length === 0) && <p className="text-sm text-muted-foreground">No jobs yet.</p>}
        <ol className="space-y-4 text-sm">
          {items?.map((item) => (
            <li key={item.id} className="flex items-center gap-3">
              <span className={`size-2 rounded-full ${item.status === "failed" ? "bg-destructive" : "bg-primary"}`} aria-hidden />
              <button type="button" onClick={() => onSelectJob?.(item.id)} className="text-left">
                <p className="font-medium">{item.type}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(item.updated_at ?? item.created_at ?? Date.now()).toLocaleString()} · {item.status}
                </p>
              </button>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
