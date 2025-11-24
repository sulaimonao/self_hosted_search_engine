"use client";

import Image from "next/image";
import { useMemo, useState } from "react";
import { CircleDotIcon, Loader2Icon, SparklesIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useBrowserTabs } from "@/lib/backend/hooks";
import { useToast } from "@/components/ui/use-toast";
import { apiClient } from "@/lib/backend/apiClient";
import { useResearchSessionLauncher } from "@/hooks/useResearchSessionLauncher";

function getDomain(url?: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.hostname || null;
  } catch {
    return null;
  }
}

export function AddressBar() {
  const tabsQuery = useBrowserTabs();
  const { toast } = useToast();
  const { startSession, isStarting } = useResearchSessionLauncher();
  const [isResearching, setIsResearching] = useState(false);

  const activeTab = useMemo(() => {
    const items = tabsQuery.data?.items ?? [];
    return items.find((tab) => tab.current_url) ?? items[0] ?? null;
  }, [tabsQuery.data?.items]);

  const domain = useMemo(() => getDomain(activeTab?.current_url), [activeTab?.current_url]);
  const tabTitle = activeTab?.current_title ?? activeTab?.current_url ?? domain ?? "Current page";

  const handleResearch = async () => {
    if (!activeTab?.current_url) {
      toast({ title: "No page selected", description: "Open a page in the embedded browser first.", variant: "warning" });
      return;
    }
    setIsResearching(true);
    try {
      await apiClient.post("/api/research/page", {
        url: activeTab.current_url,
        title: activeTab.current_title ?? domain ?? activeTab.current_url,
        source: "research_button",
      });
      await startSession(domain ?? tabTitle, activeTab.id, tabTitle);
      toast({
        title: "Research started",
        description: "Queued crawl + index for the current page and opened the research assistant.",
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to start research";
      toast({ title: "Could not start research", description: message, variant: "destructive" });
    } finally {
      setIsResearching(false);
    }
  };

  return (
    <div className="flex items-center gap-3 rounded-md border border-border-subtle bg-app-card-subtle px-3 py-2">
      <div className="flex flex-1 items-center gap-2 truncate text-sm">
        {domain ? (
          <Image
            src={`https://www.google.com/s2/favicons?domain=${domain}`}
            alt=""
            width={16}
            height={16}
            className="h-4 w-4 rounded-sm"
            referrerPolicy="no-referrer"
          />
        ) : (
          <CircleDotIcon className="h-4 w-4 text-muted-foreground" aria-hidden />
        )}
        <div className="flex flex-col truncate leading-tight">
          <span className="truncate font-medium text-foreground">{domain ?? "domain unavailable"}</span>
          <span className="truncate text-xs text-muted-foreground">{tabTitle}</span>
        </div>
      </div>
      <Button
        type="button"
        variant="secondary"
        className="gap-2"
        onClick={handleResearch}
        disabled={isResearching || isStarting}
      >
        {isResearching || isStarting ? <Loader2Icon className="h-4 w-4 animate-spin" /> : <SparklesIcon className="h-4 w-4" />}
        Research
      </Button>
    </div>
  );
}
