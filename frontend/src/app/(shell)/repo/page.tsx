"use client";

import { useMemo, useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { RepoAiFlow } from "@/app/(shell)/repo/components/RepoAiFlow";
import { RepoChangeDetail } from "@/app/(shell)/repo/components/RepoChangeDetail";
import { RepoChangesTable, type RepoChange } from "@/app/(shell)/repo/components/RepoChangesTable";
import { RepoList } from "@/app/(shell)/repo/components/RepoList";
import { RepoStatusCard } from "@/app/(shell)/repo/components/RepoStatusCard";
import { useRepoList, useRepoStatus } from "@/lib/backend/hooks";
import { ROUTES } from "@/lib/navigation";

const MOCK_CHANGES: RepoChange[] = [
  { id: "c1", title: "Upgrade dependencies", status: "Proposed", summary: "Pin webpack + eslint", jobId: "job-3312" },
  { id: "c2", title: "Improve telemetry", status: "Applied", summary: "Instrument browser runtime", jobId: "job-3301" },
];

export default function RepoPage() {
  const repoListQuery = useRepoList();
  const [selectedRepoId, setSelectedRepoId] = useState<string | null>(null);
  const [selectedChangeId, setSelectedChangeId] = useState<string | null>(null);
  const repoStatus = useRepoStatus(selectedRepoId);
  const repos = useMemo(() => repoListQuery.data?.items ?? [], [repoListQuery.data?.items]);
  const searchParams = useSearchParams();
  const router = useRouter();

  const repoFromQuery = searchParams.get("repo");

  useEffect(() => {
    if (repoFromQuery) {
      setSelectedRepoId(repoFromQuery);
    }
  }, [repoFromQuery]);

  useEffect(() => {
    if (!repoFromQuery && !selectedRepoId && repos.length) {
      setSelectedRepoId(repos[0].id);
    }
  }, [repoFromQuery, repos, selectedRepoId]);

  const selectedChange = MOCK_CHANGES.find((change) => change.id === selectedChangeId);

  function handleChangeSelect(change: RepoChange) {
    setSelectedChangeId(change.id);
    if (change.jobId) {
      router.push(`${ROUTES.activity}?job=${change.jobId}`);
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Repo</h1>
        <p className="text-sm text-muted-foreground">AI-assisted workflows for connected repositories.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        <RepoList
          repos={repos}
          selectedRepoId={selectedRepoId}
          onSelect={setSelectedRepoId}
          isLoading={repoListQuery.isLoading}
          error={repoListQuery.error?.message ?? null}
          onRetry={() => repoListQuery.refetch()}
        />
        <RepoStatusCard
          status={repoStatus.data}
          isLoading={repoStatus.isLoading}
          error={repoStatus.error?.message ?? null}
          onRetry={() => repoStatus.refetch()}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RepoAiFlow repoId={selectedRepoId} />
        <RepoChangesTable
          changes={MOCK_CHANGES}
          selectedChangeId={selectedChangeId}
          onSelectChange={handleChangeSelect}
        />
      </div>
      <RepoChangeDetail change={selectedChange} />
    </div>
  );
}
