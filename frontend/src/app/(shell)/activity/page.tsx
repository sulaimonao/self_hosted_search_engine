"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { JobDetailDrawer } from "@/app/(shell)/activity/components/JobDetailDrawer";
import { JobsFilters } from "@/app/(shell)/activity/components/JobsFilters";
import { JobsTable } from "@/app/(shell)/activity/components/JobsTable";
import { useJobDetail, useJobs } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";
import { ROUTES } from "@/lib/navigation";

export default function ActivityPage() {
  const searchParams = useSearchParams();
  const initialJob = searchParams.get("job");
  const router = useRouter();
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(initialJob);
  const jobsQuery = useJobs({
    status: status !== "all" ? status : undefined,
    type: type || undefined,
    limit: 50,
  });
  const jobDetail = useJobDetail(selectedJobId);
  const { selectThread } = useChatThread();

  useEffect(() => {
    if (!initialJob) return;
    setSelectedJobId(initialJob);
  }, [initialJob]);

  useEffect(() => {
    const current = searchParams.toString();
    const params = new URLSearchParams(current);
    if (selectedJobId) {
      params.set("job", selectedJobId);
    } else {
      params.delete("job");
    }
    const next = params.toString();
    if (next === current) return;
    router.replace(`${ROUTES.activity}${next ? `?${next}` : ""}`, { scroll: false });
  }, [router, searchParams, selectedJobId]);

  const jobs = useMemo(() => jobsQuery.data?.jobs ?? [], [jobsQuery.data?.jobs]);

  function handleThreadOpen(threadId: string) {
    selectThread(threadId);
    router.push(ROUTES.browse);
  }

  function handleRepoOpen() {
    router.push(ROUTES.repo);
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Activity</h1>
        <p className="text-sm text-muted-foreground">HydraFlow jobs and ongoing automation.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <JobsTable
          jobs={jobs}
          isLoading={jobsQuery.isLoading}
          error={jobsQuery.error?.message ?? null}
          selectedJobId={selectedJobId}
          onSelectJob={setSelectedJobId}
          onRetry={() => jobsQuery.refetch()}
        />
        <JobsFilters status={status} type={type} onStatusChange={setStatus} onTypeChange={setType} />
      </div>
      <JobDetailDrawer
        job={jobDetail.data?.job}
        isLoading={jobDetail.isLoading}
        error={jobDetail.error?.message ?? null}
        onOpenThread={jobDetail.data?.job?.thread_id ? handleThreadOpen : undefined}
        onOpenRepo={jobDetail.data?.job?.type?.startsWith("repo_") ? handleRepoOpen : undefined}
      />
    </div>
  );
}
