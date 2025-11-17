import { ActivityTimeline } from "@/components/overview/ActivityTimeline";
import { OverviewCards } from "@/components/overview/OverviewCards";
import { SessionsList } from "@/components/overview/SessionsList";

const cards = [
  { title: "Documents", value: "12,481", description: "Indexed across HydraFlow" },
  { title: "Memories", value: "384", description: "Linked to chat threads" },
  { title: "Browser tabs", value: "7", description: "Active with capture enabled" },
  { title: "Storage", value: "64%", description: "Of allotted disk used" },
];

const sessions = [
  { id: "s1", title: "Search quality sync", timestamp: "5m ago", summary: "Compared serp across threads." },
  { id: "s2", title: "Repo triage", timestamp: "28m ago", summary: "Outlined failing tests and patches." },
  { id: "s3", title: "Privacy audit", timestamp: "1h ago", summary: "Reviewed retention policy." },
];

const activity = [
  { id: "a1", title: "Bundle export", timestamp: "Just now", status: "Queued" },
  { id: "a2", title: "Repo checks", timestamp: "17m ago", status: "Passing" },
  { id: "a3", title: "Domain crawl", timestamp: "1h ago", status: "Completed" },
];

export default function HomePage() {
  return (
    <div className="flex flex-1 flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="text-sm text-muted-foreground">HydraFlow status and AI activity at a glance.</p>
      </div>
      <OverviewCards cards={cards} />
      <div className="grid gap-6 lg:grid-cols-2">
        <SessionsList sessions={sessions} />
        <ActivityTimeline items={activity} />
      </div>
    </div>
  );
}
