"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertCircleIcon, Loader2Icon, PlusIcon, SparklesIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import { useBrowserTabs } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";

export function TabStrip() {
  const { data, isLoading, error, refetch } = useBrowserTabs();
  const { selectThread, startThread, currentThreadId } = useChatThread();
  const { toast } = useToast();
  const tabs = useMemo(() => data?.items ?? [], [data?.items]);
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    if (!activeId && tabs.length) {
      setActiveId(tabs[0].id);
      if (tabs[0].thread_id) {
        selectThread(tabs[0].thread_id);
      }
    }
  }, [activeId, selectThread, tabs]);

  useEffect(() => {
    function handleNewTabHotkey(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey)) return;
      if (event.key.toLowerCase() !== "t") return;
      event.preventDefault();
      void handleNewTab();
    }

    window.addEventListener("keydown", handleNewTabHotkey);
    return () => window.removeEventListener("keydown", handleNewTabHotkey);
  }, [handleNewTab]);

  const activeThreadId = useMemo(() => {
    if (!activeId) return null;
    return tabs.find((tab) => tab.id === activeId)?.thread_id ?? null;
  }, [activeId, tabs]);

  useEffect(() => {
    if (activeThreadId && currentThreadId !== activeThreadId) {
      selectThread(activeThreadId);
    }
  }, [activeThreadId, currentThreadId, selectThread]);

  const handleSelect = useCallback(
    async (tabId: string) => {
      setActiveId(tabId);
      const tab = tabs.find((candidate) => candidate.id === tabId);
      if (!tab) return;
      if (tab.thread_id) {
        selectThread(tab.thread_id);
        return;
      }
      try {
        const threadId = await startThread({ tabId, title: tab.current_title ?? tab.current_url ?? "New tab", origin: "browser" });
        selectThread(threadId);
      } catch (err) {
        toast({ title: "Unable to link tab", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
      }
    },
    [selectThread, startThread, tabs, toast],
  );

  const handleNewTab = useCallback(async () => {
    try {
      const threadId = await startThread({ origin: "browser" });
      selectThread(threadId);
      toast({ title: "New browser tab", description: "Linked to a fresh AI thread." });
    } catch (err) {
      toast({ title: "Unable to start tab", description: err instanceof Error ? err.message : "Unknown error", variant: "destructive" });
    }
  }, [selectThread, startThread, toast]);

  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-background px-3 py-2">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Tabs</span>
        {isLoading && <Loader2Icon className="size-3.5 animate-spin" />}
        {error && (
          <button type="button" className="flex items-center gap-1 text-destructive" onClick={() => refetch()}>
            <AlertCircleIcon className="size-3.5" /> {error.message ?? "Retry"}
          </button>
        )}
      </div>
      <div className="flex items-center gap-2 overflow-x-auto">
        {!isLoading && !tabs.length && <p className="text-sm text-muted-foreground">No browser tabs are currently linked.</p>}
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab.id}
            onClick={() => handleSelect(tab.id)}
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition ${tab.id === activeId ? "border-primary bg-primary/10 text-primary" : "border-transparent bg-muted text-muted-foreground hover:bg-muted/80"}`}
          >
            <span className="max-w-[140px] truncate">{tab.current_title ?? tab.current_url ?? tab.id}</span>
            {tab.thread_id && <SparklesIcon className="size-3 text-primary" aria-label="Thread linked" />}
          </button>
        ))}
        <Button variant="ghost" size="icon" onClick={handleNewTab} title="New browser tab (⌘T)">
          <PlusIcon className="size-4" />
          <span className="sr-only">New browser tab</span>
        </Button>
      </div>
    </div>
  );
}
