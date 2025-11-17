"use client";

import { useMemo, useState } from "react";

import { RepoAiFlow } from "@/app/(shell)/repo/components/RepoAiFlow";
import { RepoChangeDetail } from "@/app/(shell)/repo/components/RepoChangeDetail";
import { RepoChangesTable } from "@/app/(shell)/repo/components/RepoChangesTable";
import { RepoList } from "@/app/(shell)/repo/components/RepoList";
import { RepoStatusCard } from "@/app/(shell)/repo/components/RepoStatusCard";
import { useRepoList, useRepoStatus } from "@/lib/backend/hooks";

export default function RepoPage() {
  const repoListQuery = useRepoList();
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const repoStatus = useRepoStatus(selectedRepoId);
  const repos = useMemo(() => repoListQuery.data?.items ?? [], [repoListQuery.data?.items]);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Repo</h1>
        <p className="text-sm text-muted-foreground">AI-assisted workflows for connected repositories.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        <RepoList repos={repos} selectedRepoId={selectedRepoId} onSelect={setSelectedRepoId} />
        <RepoStatusCard status={repoStatus.data} isLoading={repoStatus.isLoading} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RepoAiFlow repoId={selectedRepoId} />
        <RepoChangesTable />
      </div>
      <RepoChangeDetail />
    </div>
  );
}
