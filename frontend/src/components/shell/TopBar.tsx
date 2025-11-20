"use client";

import { BellIcon, CircleDotIcon, CommandIcon, HelpCircleIcon, PlusIcon, SparklesIcon } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { StartResearchSessionDialog } from "@/components/research/StartResearchSessionDialog";
import { useBrowserTabs } from "@/lib/backend/hooks";

interface TopBarProps {
  onCommandPalette: () => void;
  aiPanelOpen: boolean;
  onToggleAiPanel: () => void;
}

export function TopBar({ onCommandPalette, aiPanelOpen, onToggleAiPanel }: TopBarProps) {
  const tabsQuery = useBrowserTabs();
  const activeTab = useMemo(() => {
    const items = tabsQuery.data?.items ?? [];
    return items.find((tab) => tab.current_url) ?? items[0] ?? null;
  }, [tabsQuery.data?.items]);

  const domain = useMemo(() => {
    const raw = activeTab?.current_url;
    if (!raw) return null;
    try {
      return new URL(raw).hostname || null;
    } catch {
      return null;
    }
  }, [activeTab?.current_url]);

  return (
    <header className="border-b border-border-subtle bg-app-elevated/95 text-fg backdrop-blur supports-[backdrop-filter]:bg-app-elevated/75">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4">
        <div className="font-semibold tracking-tight text-fg">Self Hosted Copilot</div>
        <div className="hidden flex-1 items-center gap-2 rounded-xs border border-border-subtle bg-app-subtle/70 px-3 py-1 text-sm text-fg-muted lg:flex">
          <CommandIcon className="size-4" />
          <span>Type / to ask anything</span>
        </div>
        <div className="flex flex-1 items-center gap-3 lg:max-w-sm">
          <div className="flex w-full items-center gap-2 rounded-md border border-border-subtle bg-app-input px-3 py-2 text-left text-sm">
            {domain ? (
              <img
                src={`https://www.google.com/s2/favicons?domain=${domain}`}
                alt=""
                className="h-4 w-4 rounded-sm"
                referrerPolicy="no-referrer"
              />
            ) : (
              <CircleDotIcon className="h-4 w-4 text-muted-foreground" aria-hidden />
            )}
            <div className="truncate">
              <div className="truncate font-medium text-foreground">{domain ?? "domain unavailable"}</div>
              <div className="truncate text-xs text-muted-foreground">
                {activeTab?.current_title ?? activeTab?.current_url ?? "No page loaded"}
              </div>
            </div>
          </div>
        </div>
        <StartResearchSessionDialog
          trigger={
            <Button size="sm" className="bg-accent text-fg-on-accent hover:bg-accent/90">
              <PlusIcon className="mr-2 size-4" />
              New session
            </Button>
          }
        />
        <Button variant={aiPanelOpen ? "secondary" : "outline"} size="sm" onClick={onToggleAiPanel}>
          <SparklesIcon className="mr-2 size-4" />
          {aiPanelOpen ? "Hide AI" : "Show AI"}
          <span className="ml-2 hidden text-[11px] text-fg-muted sm:inline">⌘⇧A</span>
        </Button>
        <Button variant="outline" size="sm" onClick={onCommandPalette}>
          <CommandIcon className="mr-2 size-4" />
          Command + K
        </Button>
        <Button variant="ghost" size="icon">
          <HelpCircleIcon className="size-5" />
        </Button>
        <Button variant="ghost" size="icon">
          <BellIcon className="size-5" />
        </Button>
      </div>
    </header>
  );
}
