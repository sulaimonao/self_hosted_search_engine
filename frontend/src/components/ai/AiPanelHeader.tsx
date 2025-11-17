"use client";

import { useMemo } from "react";
import { GlobeIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { useBrowserTabs } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";
import { cn } from "@/lib/utils";

export function AiPanelHeader() {
  const { currentThreadId, isLoading } = useChatThread();
  const tabsQuery = useBrowserTabs();

  const linkedTab = useMemo(() => {
    if (!currentThreadId) return null;
    return tabsQuery.data?.items?.find((tab) => tab.thread_id === currentThreadId) ?? null;
  }, [currentThreadId, tabsQuery.data?.items]);

  const domain = useMemo(() => {
    if (!linkedTab?.current_url) return null;
    try {
      const url = new URL(linkedTab.current_url);
      return url.hostname;
    } catch {
      return null;
    }
  }, [linkedTab?.current_url]);

  const status = tabsQuery.isLoading || isLoading ? "Syncing…" : linkedTab ? "Linked" : "Unbound";

  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-fg-subtle">AI Copilot</p>
          <p className="font-semibold text-fg">
            {linkedTab?.current_title ?? (currentThreadId ? `Thread ${currentThreadId.slice(0, 8)}` : "Connect a thread")}
          </p>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "border px-2 py-0.5 text-[11px]",
            linkedTab
              ? "border-accent/60 bg-accent-soft text-fg"
              : "border-border-subtle text-fg-muted"
          )}
        >
          {status}
        </Badge>
      </div>
      <div className="mt-2 flex items-center gap-2 text-xs text-fg-muted">
        <GlobeIcon className="size-3.5" aria-hidden />
        <span className="truncate">{domain ?? linkedTab?.current_url ?? "Unbound tab"}</span>
      </div>
    </div>
  );
}
