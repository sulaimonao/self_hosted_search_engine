"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ActivityTimeline } from "@/components/overview/ActivityTimeline";
import { OverviewCards } from "@/components/overview/OverviewCards";
import { SessionsList } from "@/components/overview/SessionsList";
import { useOverview, useThreads, useJobs } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";
import { ROUTES } from "@/lib/navigation";
import { setAiPanelSessionOpen } from "@/lib/uiSession";
import type { OverviewCardProps } from "@/components/overview/OverviewCard";

const numberFormatter = new Intl.NumberFormat("en-US");

export default function HomePage() {
  const router = useRouter();
  const { selectThread } = useChatThread();
  const overview = useOverview();
  const threads = useThreads(5);
  const jobs = useJobs({ limit: 5 });

  const cards: OverviewCardProps[] = useMemo(() => {
    if (!overview.data) return [];
    return [
      {
        title: "Documents",
        value: numberFormatter.format(overview.data.knowledge.documents ?? 0),
        description: "Normalized across HydraFlow",
      },
      {
        title: "Memories",
        value: numberFormatter.format(overview.data.llm.memories.total ?? 0),
        description: "Stored against chat threads",
      },
      {
        title: "Browser tabs",
        value: numberFormatter.format(overview.data.browser.tabs.linked ?? 0),
        description: "Linked to AI sessions",
      },
      {
        title: "History rows",
        value: numberFormatter.format(overview.data.browser.history.entries ?? 0),
        description: "Captured from local browsing",
      },
    ];
  }, [overview.data]);

  const handleThreadSelect = (threadId: string) => {
    selectThread(threadId);
    setAiPanelSessionOpen(true);
    router.push(ROUTES.browse);
  };

  const handleJobSelect = (jobId: string) => {
    router.push(`${ROUTES.activity}?job=${jobId}`);
  };

  return (
    <div className="flex flex-1 flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">HydraFlow status and AI activity at a glance.</p>
      </div>
      <OverviewCards
        cards={cards}
        isLoading={overview.isLoading}
        error={overview.error?.message ?? null}
        onRetry={() => overview.refetch()}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <SessionsList
          threads={threads.data?.items}
          isLoading={threads.isLoading}
          error={threads.error?.message ?? null}
          onSelectThread={handleThreadSelect}
          onRetry={() => threads.refetch()}
        />
        <ActivityTimeline
          items={jobs.data?.jobs}
          isLoading={jobs.isLoading}
          error={jobs.error?.message ?? null}
          onSelectJob={handleJobSelect}
          onRetry={() => jobs.refetch()}
        />
      </div>
    </div>
  );
}
