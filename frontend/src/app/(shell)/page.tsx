"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ActivityTimeline } from "@/components/overview/ActivityTimeline";
import { OverviewCards } from "@/components/overview/OverviewCards";
import { SessionsList } from "@/components/overview/SessionsList";
import { Button } from "@/components/ui/button";
import { StartResearchSessionDialog } from "@/components/research/StartResearchSessionDialog";
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
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-2xl border border-border-subtle bg-app-card p-6 shadow-subtle">
          <p className="text-xs uppercase tracking-wide text-fg-muted">Research cockpit</p>
          <h1 className="mt-2 text-2xl font-semibold text-fg">Start a new research session</h1>
          <p className="mt-2 text-sm text-fg-muted">
            Open a browsing tab, capture sources, and ask the AI to summarize or create tasks with full context.
          </p>
          <div className="mt-4">
            <StartResearchSessionDialog
              trigger={
                <Button className="bg-accent text-fg-on-accent hover:bg-accent/90">
                  Start new research session
                </Button>
              }
            />
          </div>
        </div>
        <div className="rounded-2xl border border-border-subtle bg-app-card-subtle p-6">
          <p className="text-sm font-semibold text-fg">Flow</p>
          <ol className="mt-3 space-y-2 text-sm text-fg-muted">
            <li>1. Launch a session with an optional topic.</li>
            <li>2. Browse and capture pages into notes.</li>
            <li>3. Chat with AI, create tasks, and export the bundle.</li>
          </ol>
        </div>
      </div>
      <div>
        <h2 className="text-2xl font-semibold">Overview</h2>
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
