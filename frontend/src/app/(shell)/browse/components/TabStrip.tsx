"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2Icon, PlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useBrowserTabs } from "@/lib/backend/hooks";
import { useChatThread } from "@/lib/useChatThread";

export function TabStrip() {
  const { data, isLoading } = useBrowserTabs();
  const { selectThread, startThread, currentThreadId } = useChatThread();
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

  const activeThreadId = useMemo(() => {
    if (!activeId) return null;
    return tabs.find((tab) => tab.id === activeId)?.thread_id ?? null;
  }, [activeId, tabs]);

  useEffect(() => {
    if (activeThreadId && currentThreadId !== activeThreadId) {
      selectThread(activeThreadId);
    }
  }, [activeThreadId, currentThreadId, selectThread]);

  async function handleSelect(tabId: string) {
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
    } catch (error) {
      console.error("Unable to link tab", error);
    }
  }

  async function handleNewChat() {
    try {
      const threadId = await startThread({ origin: "chat" });
      selectThread(threadId);
    } catch (error) {
      console.error("Unable to start chat", error);
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-xl border bg-background px-3 py-2">
      <div className="flex flex-1 items-center gap-2 overflow-x-auto">
        {isLoading && <Loader2Icon className="size-4 animate-spin text-muted-foreground" />}
        {!isLoading && !tabs.length && <p className="text-sm text-muted-foreground">No browser tabs are currently linked.</p>}
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab.id}
            onClick={() => handleSelect(tab.id)}
            className={`flex items-center gap-2 rounded-full px-3 py-1 text-sm ${tab.id === activeId ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}
          >
            <span className="max-w-[140px] truncate">{tab.current_title ?? tab.current_url ?? tab.id}</span>
          </button>
        ))}
      </div>
      <Button variant="ghost" size="icon" onClick={handleNewChat}>
        <PlusIcon className="size-4" />
      </Button>
    </div>
  );
}
