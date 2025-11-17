"use client";

import { useCallback, useMemo, useState } from "react";

import { useToast } from "@/components/ui/use-toast";
import { apiClient } from "@/lib/backend/apiClient";
import { exportResearchSessionBundle } from "@/lib/researchSession";
import { useChatThread } from "@/lib/useChatThread";
import { useBrowserTabs } from "@/lib/backend/hooks";

export function useResearchSessionActions() {
  const { currentThreadId, currentThread, sendMessage } = useChatThread();
  const tabsQuery = useBrowserTabs();
  const { toast } = useToast();
  const [isAddingPage, setIsAddingPage] = useState(false);
  const [isSummarizingPage, setIsSummarizingPage] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const linkedTab = useMemo(() => {
    const tabs = tabsQuery.data?.items ?? [];
    return tabs.find((tab) => tab.thread_id === currentThreadId) ?? null;
  }, [currentThreadId, tabsQuery.data?.items]);

  const requireSession = useCallback(() => {
    if (!currentThreadId) {
      toast({ title: "No active session", description: "Start a research session to use this action.", variant: "warning" });
      return false;
    }
    return true;
  }, [currentThreadId, toast]);

  const addPageToSession = useCallback(async () => {
    if (!requireSession()) return;
    if (!linkedTab?.current_url) {
      toast({ title: "No page available", description: "Open a page in the linked tab first.", variant: "warning" });
      return;
    }
    setIsAddingPage(true);
    try {
      await apiClient.post("/api/memory", {
        thread_id: currentThreadId,
        title: linkedTab.current_title ?? linkedTab.current_url,
        content: `${linkedTab.current_title ?? "Untitled page"}\n${linkedTab.current_url}`,
        metadata: {
          tab_id: linkedTab.id,
          url: linkedTab.current_url,
          type: "browser_page",
        },
      });
      toast({ title: "Page captured", description: "Added to session notes." });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to save page";
      toast({ title: "Unable to save page", description: message, variant: "destructive" });
      throw error;
    } finally {
      setIsAddingPage(false);
    }
  }, [currentThreadId, linkedTab, requireSession, toast]);

  const summarizePageToNotes = useCallback(async () => {
    if (!requireSession()) return;
    if (!linkedTab?.id) {
      toast({ title: "No tab linked", description: "Link a browser tab to this session first.", variant: "warning" });
      return;
    }
    setIsSummarizingPage(true);
    try {
      const title = linkedTab.current_title ?? linkedTab.current_url ?? "this page";
      const response = await sendMessage({
        content: `Summarize the current page (${title}). Highlight the key claims, evidence, and data points in bullet form for my research notes.`,
        tabId: linkedTab.id,
      });
      const summary = response?.message || response?.answer;
      if (summary) {
        await apiClient.post("/api/memory", {
          thread_id: currentThreadId,
          title: `Summary – ${title}`,
          content: summary,
          metadata: {
            tab_id: linkedTab.id,
            url: linkedTab.current_url,
            type: "page_summary",
          },
        });
      }
      toast({ title: "Page summarized", description: summary ? "Saved to session notes." : "AI response logged in chat." });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to summarize";
      toast({ title: "Unable to summarize", description: message, variant: "destructive" });
      throw error;
    } finally {
      setIsSummarizingPage(false);
    }
  }, [currentThreadId, linkedTab, requireSession, sendMessage, toast]);

  const exportSession = useCallback(async () => {
    if (!currentThread) {
      toast({ title: "No thread selected", description: "Select a research session first.", variant: "warning" });
      return;
    }
    setIsExporting(true);
    try {
      const bundle = await exportResearchSessionBundle(currentThread);
      toast({
        title: "Export started",
        description: `Job ${bundle.job_id} is running. Check Activity to download the bundle.`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to export";
      toast({ title: "Unable to export", description: message, variant: "destructive" });
      throw error;
    } finally {
      setIsExporting(false);
    }
  }, [currentThread, toast]);

  return {
    linkedTab,
    tabsQuery,
    addPageToSession,
    summarizePageToNotes,
    exportSession,
    isAddingPage,
    isSummarizingPage,
    isExporting,
    hasSession: Boolean(currentThreadId),
  };
}
