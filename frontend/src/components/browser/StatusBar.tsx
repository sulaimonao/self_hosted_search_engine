"use client";

import { useMemo } from "react";
import { useShallow } from "zustand/react/shallow";

import { useHealth } from "@/lib/health";
import { useAppStore } from "@/state/useAppStore";

function resolveHealthColor(status: string | undefined) {
  switch (status) {
    case "ok":
      return "bg-green-500";
    case "degraded":
      return "bg-amber-500";
    default:
      return "bg-red-500";
  }
}

export function StatusBar() {
  const notifications = useAppStore(useShallow((state) => state.notifications));
  const health = useHealth();

  const crawl = useMemo(() => {
    const entries = Object.values(notifications).filter((item) => item.kind === "crawl.progress");
    if (!entries.length) return undefined;
    return entries.sort((a, b) => b.latest - a.latest)[0];
  }, [notifications]);

  const queueCount = useMemo(() => {
    return Object.values(notifications)
      .filter((item) => item.kind === "crawl.start")
      .reduce((total, item) => total + item.count, 0);
  }, [notifications]);

  return (
    <footer className="flex h-9 items-center justify-between border-t bg-background/80 px-4 text-xs backdrop-blur">
      <div className="truncate">
        {crawl
          ? `Crawling ${crawl.site ?? "unknown"} (${Math.round(crawl.progress ?? 0)}%)`
          : "Idle"}
      </div>
      <div>Jobs queued: {queueCount}</div>
      <div className="flex items-center gap-2">
        <span className={`inline-flex h-2.5 w-2.5 rounded-full ${resolveHealthColor(health?.status)}`} />
        API
      </div>
    </footer>
  );
}
