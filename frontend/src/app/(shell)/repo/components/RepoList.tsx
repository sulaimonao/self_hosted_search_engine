"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { RepoRecord } from "@/lib/backend/types";

interface RepoListProps {
  repos?: RepoRecord[];
  selectedRepoId?: string | null;
  onSelect?: (repoId: string) => void;
}

export function RepoList({ repos, selectedRepoId, onSelect }: RepoListProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Repositories</CardTitle>
        <CardDescription>Link status with HydraFlow repo tools.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!repos?.length && <p className="text-sm text-muted-foreground">No repos registered yet.</p>}
        {repos?.map((repo) => (
          <button
            key={repo.id}
            type="button"
            onClick={() => onSelect?.(repo.id)}
            className={`w-full rounded-xl border p-3 text-left text-sm ${selectedRepoId === repo.id ? "border-primary" : ""}`}
          >
            <p className="font-semibold">{repo.id}</p>
            <p className="text-muted-foreground">{repo.root_path}</p>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
