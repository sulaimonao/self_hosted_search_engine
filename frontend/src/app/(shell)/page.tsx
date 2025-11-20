"use client";

import type React from "react";
import Link from "next/link";
import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { ActivityTimeline } from "@/components/overview/ActivityTimeline";
import { OverviewCards } from "@/components/overview/OverviewCards";
import { SessionsList } from "@/components/overview/SessionsList";
import { Button } from "@/components/ui/button";
import { StartResearchSessionDialog } from "@/components/research/StartResearchSessionDialog";
import { ArrowRight, Compass, Database, Search, Sparkles } from "lucide-react";
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

  const heroStats = [
    {
      label: "Documents",
      value: overview.data ? numberFormatter.format(overview.data.knowledge.documents ?? 0) : "—",
      hint: "Indexed and normalized",
    },
    {
      label: "Memories",
      value: overview.data ? numberFormatter.format(overview.data.llm.memories.total ?? 0) : "—",
      hint: "LLM context on hand",
    },
    {
      label: "Active jobs",
      value: numberFormatter.format(jobs.data?.jobs?.length ?? 0),
      hint: "Pipelines in motion",
    },
  ];

  const lastJob = jobs.data?.jobs?.[0];
  const lastJobTime = lastJob?.updated_at ?? lastJob?.created_at;
  const lastJobLine = lastJob ? `${lastJob.type} · ${lastJob.status}` : "Standing by for the next run";

  return (
    <div className="relative flex flex-1 flex-col gap-8">
      <div className="pointer-events-none absolute -left-28 -top-32 h-64 w-64 rounded-full bg-primary/10 blur-3xl" aria-hidden />
      <div className="pointer-events-none absolute -right-20 bottom-0 h-72 w-72 rounded-full bg-secondary/50 blur-3xl" aria-hidden />

      <section className="relative overflow-hidden rounded-2xl border border-border-subtle bg-card/80 shadow-soft">
        <div className="absolute inset-0 bg-gradient-to-r from-primary/8 via-transparent to-secondary/30" aria-hidden />
        <div className="relative grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="flex flex-col gap-5 p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Command center</p>
            <div className="space-y-3">
              <h1 className="text-3xl font-semibold text-foreground sm:text-4xl">Welcome back</h1>
              <p className="text-base text-muted-foreground">
                Your personal search engine is awake, indexing, and ready to explore. Launch a session or jump into a search
                whenever inspiration strikes.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              <StartResearchSessionDialog
                trigger={
                  <Button size="lg" className="bg-primary text-primary-foreground shadow-soft hover:bg-primary/90">
                    Start research session
                  </Button>
                }
              />
              <Button
                size="lg"
                variant="outline"
                className="border-border-subtle bg-background text-foreground hover:border-sidebar-ring hover:bg-muted/60"
                asChild
              >
                <Link href={ROUTES.search} className="flex items-center gap-2">
                  <Search className="h-4 w-4" aria-hidden />
                  Open unified search
                </Link>
              </Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {heroStats.map((stat) => (
                <HeroStatCard key={stat.label} {...stat} />
              ))}
            </div>
          </div>

          <div className="relative flex flex-col justify-center gap-4 border-t border-border-subtle/70 bg-app-card-subtle p-6 lg:border-l lg:border-t-0">
            <div className="rounded-xl border border-border-subtle bg-card/80 p-4 shadow-subtle">
              <div className="flex items-start gap-3">
                <span className="mt-1 inline-flex h-2.5 w-2.5 rounded-full bg-state-success shadow-subtle" aria-hidden />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-foreground">System steady</p>
                  <p className="text-xs text-muted-foreground">{lastJobLine}</p>
                  {lastJobTime && (
                    <p className="text-[11px] text-muted-foreground">
                      {new Date(lastJobTime).toLocaleString()}
                    </p>
                  )}
                </div>
              </div>
              <div className="mt-4 grid gap-2">
                <QuickLink
                  href={ROUTES.activity}
                  icon={Sparkles}
                  label="Monitor activity"
                  description="Follow indexing runs and automations."
                />
                <QuickLink
                  href={ROUTES.data}
                  icon={Database}
                  label="Add new data"
                  description="Point the crawler at a fresh source."
                />
                <QuickLink
                  href={ROUTES.browse}
                  icon={Compass}
                  label="Open workspace"
                  description="Capture pages and hand them to the AI."
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Overview</h2>
            <p className="text-sm text-muted-foreground">HydraFlow status and AI activity, now in desert hues.</p>
          </div>
          <Button variant="ghost" size="sm" className="text-primary hover:text-primary/80" asChild>
            <Link href={ROUTES.activity} className="inline-flex items-center gap-1">
              View activity
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </Button>
        </div>
        <OverviewCards
          cards={cards}
          isLoading={overview.isLoading}
          error={overview.error?.message ?? null}
          onRetry={() => overview.refetch()}
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <ActivityTimeline
          items={jobs.data?.jobs}
          isLoading={jobs.isLoading}
          error={jobs.error?.message ?? null}
          onSelectJob={handleJobSelect}
          onRetry={() => jobs.refetch()}
        />

        <div className="space-y-4">
          <div className="rounded-2xl border border-border-subtle bg-card/80 p-5 shadow-subtle">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" aria-hidden />
              <h3 className="text-lg font-semibold text-foreground">Quick actions</h3>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              Shortcut into the dunes: capture, search, and sanity-check your system.
            </p>
            <div className="mt-4 grid gap-3">
              <Button className="justify-start bg-primary text-primary-foreground hover:bg-primary/90" asChild>
                <Link href={ROUTES.search}>
                  <Search className="mr-2 h-4 w-4" aria-hidden />
                  Start a new search
                </Link>
              </Button>
              <Button variant="outline" className="justify-start border-border-subtle bg-background hover:bg-muted/70" asChild>
                <Link href={ROUTES.data}>
                  <Database className="mr-2 h-4 w-4" aria-hidden />
                  Add a data source
                </Link>
              </Button>
              <Button variant="ghost" className="justify-start text-foreground hover:bg-sidebar-accent" asChild>
                <Link href={ROUTES.activity}>
                  <Compass className="mr-2 h-4 w-4" aria-hidden />
                  Review recent activity
                </Link>
              </Button>
            </div>
          </div>
          <SessionsList
            threads={threads.data?.items}
            isLoading={threads.isLoading}
            error={threads.error?.message ?? null}
            onSelectThread={handleThreadSelect}
            onRetry={() => threads.refetch()}
          />
        </div>
      </div>
    </div>
  );
}

type HeroStat = {
  label: string;
  value: string;
  hint: string;
};

function HeroStatCard({ label, value, hint }: HeroStat) {
  return (
    <div className="rounded-lg border border-border-subtle bg-app-card-subtle p-3 shadow-subtle">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

type QuickLinkProps = {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  description: string;
};

function QuickLink({ href, icon: Icon, label, description }: QuickLinkProps) {
  return (
    <Link
      href={href}
      className="group flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-background px-3 py-2.5 text-sm transition-colors hover:border-sidebar-ring hover:bg-sidebar-accent"
    >
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-md bg-sidebar-accent text-sidebar-foreground">
          <Icon className="h-4 w-4" aria-hidden />
        </span>
        <div className="flex flex-col">
          <span className="font-semibold text-foreground">{label}</span>
          <span className="text-xs text-muted-foreground">{description}</span>
        </div>
      </div>
      <ArrowRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-1" aria-hidden />
    </Link>
  );
}
