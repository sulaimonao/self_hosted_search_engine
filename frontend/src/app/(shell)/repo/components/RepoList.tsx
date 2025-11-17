"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repositories</CardTitle>
        <CardDescription>Link status with HydraFlow repo tools.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-24 w-full" />}
        {error && (
          <div className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <p>{error}</p>
            <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
          </div>
        )}
        {!isLoading && !error && !repos?.length && <p className="text-sm text-muted-foreground">No repos registered yet.</p>}
        {repos?.map((repo) => (
          <button
            key={repo.id}
            type="button"
            onClick={() => onSelect?.(repo.id)}
            className={`w-full rounded-xl border p-3 text-left text-sm transition ${selectedRepoId === repo.id ? "border-primary bg-primary/5" : "border-border/60 hover:border-primary/50"}`}
          >
            <p className="font-semibold">{repo.id}</p>
            <p className="text-muted-foreground">{repo.root_path}</p>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
