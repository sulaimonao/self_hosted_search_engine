"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";

import { useToast } from "@/components/ui/use-toast";
import { useBrowserTabs } from "@/lib/backend/hooks";
import { ROUTES } from "@/lib/navigation";
import { createResearchSession } from "@/lib/researchSession";
import { setAiPanelSessionOpen } from "@/lib/uiSession";
import { useChatThread } from "@/lib/useChatThread";

export function useResearchSessionLauncher() {
  const router = useRouter();
  const { selectThread } = useChatThread();
  const tabsQuery = useBrowserTabs();
  const { toast } = useToast();
  const [isStarting, setIsStarting] = useState(false);

  const startSession = useCallback(
    async (topic?: string) => {
      setIsStarting(true);
      try {
        const tabs = tabsQuery.data?.items ?? [];
        const availableTab = tabs.find((tab) => !tab.thread_id) ?? tabs[0];
        const session = await createResearchSession({
          topic,
          tabId: availableTab?.id,
          tabTitle: availableTab?.current_title ?? availableTab?.current_url ?? undefined,
        });
        selectThread(session.threadId);
        setAiPanelSessionOpen(true);
        router.push(ROUTES.browse);
        toast({
          title: session.topic ? `Researching ${session.topic}` : "New research session",
          description: availableTab ? "Linked to your active browser tab." : "Thread ready for browsing.",
        });
        return session;
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to start session";
        toast({ title: "Could not start session", description: message, variant: "destructive" });
        throw error;
      } finally {
        setIsStarting(false);
      }
    },
    [router, selectThread, tabsQuery.data?.items, toast],
  );

  return { startSession, isStarting };
}
