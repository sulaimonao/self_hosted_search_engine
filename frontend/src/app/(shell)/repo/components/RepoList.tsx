"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { RepoRecord } from "@/lib/backend/types";

interface RepoListProps {
  repos?: RepoRecord[];
  selectedRepoId?: string | null;
  onSelect?: (repoId: string) => void;
  isLoading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export function RepoList({ repos, selectedRepoId, onSelect, isLoading, error, onRetry }: RepoListProps) {
  const rowClasses =
    "w-full rounded-xs border border-transparent px-3 py-2 text-left text-sm transition-colors duration-fast hover:border-border-subtle hover:bg-app-card-hover cursor-pointer";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Repositories</CardTitle>
        <CardDescription>Link status with HydraFlow repo tools.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-24 w-full" />}
        {error && (
          <div className="space-y-2 rounded-md border border-state-danger/40 bg-state-danger/10 p-3 text-sm text-state-danger">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && !repos?.length && <p className="text-sm text-fg-muted">No repos registered yet.</p>}
        {repos?.map((repo) => (
          <button
            key={repo.id}
            type="button"
            onClick={() => onSelect?.(repo.id)}
            className={cn(rowClasses, selectedRepoId === repo.id && "border-accent bg-accent-soft text-fg")}
          >
            <p className="font-semibold text-fg">{repo.id}</p>
            <p className="text-fg-muted">{repo.root_path}</p>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
