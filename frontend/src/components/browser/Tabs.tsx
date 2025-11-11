"use client";

import { EyeOff, Plus, X } from "lucide-react";
import { useId, useMemo } from "react";
import { useShallow } from "zustand/react/shallow";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/state/useAppStore";
import { DEFAULT_NEW_TAB_URL } from "@/components/browser/constants";

export function TabsBar() {
  const { tabs, activeTabId, setActive, closeTab, addTab, incognitoMode, setIncognitoMode } = useAppStore(
    useShallow((state) => ({
      tabs: state.tabs,
      activeTabId: state.activeTabId,
      setActive: state.setActive,
      closeTab: state.closeTab,
      addTab: state.addTab,
      incognitoMode: state.incognitoMode,
      setIncognitoMode: state.setIncognitoMode,
    })),
  );

  const resolvedActiveTabId = activeTabId ?? tabs[0]?.id;

  const sorted = useMemo(() => tabs, [tabs]);
  const newTabDescriptionId = useId();
  const incognitoDescriptionId = useId();

  return (
    <div className="flex items-center gap-2">
      <div className="max-w-full overflow-x-auto">
        <div className="flex items-center gap-2 py-1" role="tablist" aria-label="Browser tabs">
          {sorted.map((tab) => {
            const active = resolvedActiveTabId === tab.id;
            const closeDescriptionId = makeTabDomId("tab-close-desc", tab.id);
            return (
              <button
                key={tab.id}
                type="button"
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition",
                  active ? "bg-background shadow" : "bg-muted text-muted-foreground hover:text-foreground",
                )}
                onClick={() => setActive(tab.id)}
                title={tab.url}
                role="tab"
                aria-selected={active}
                tabIndex={active ? 0 : -1}
              >
                {tab.favicon ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={tab.favicon} alt="" className="h-3 w-3" />
                ) : null}
                {tab.incognito ? <EyeOff size={12} className="h-3 w-3 text-muted-foreground" /> : null}
                <span className="max-w-[200px] truncate">{tab.title || tab.url || "New Tab"}</span>
                {tabs.length > 1 ? (
                  <span
                    role="button"
                    tabIndex={0}
                    aria-label={`Close ${tab.title || tab.url || "tab"}`}
                    aria-describedby={closeDescriptionId}
                    className="shrink-0 rounded-full p-0.5 text-muted-foreground outline-none transition hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    onClick={(event) => {
                      event.stopPropagation();
                      closeTab(tab.id);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        event.stopPropagation();
                        closeTab(tab.id);
                      }
                    }}
                  >
                    <X size={14} aria-hidden="true" />
                    <span id={closeDescriptionId} className="sr-only">
                      Close tab {tab.title || tab.url || "New Tab"}
                    </span>
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      <Button
        size="icon"
        variant="outline"
        onClick={() => addTab(DEFAULT_NEW_TAB_URL)}
        title="New tab"
        aria-label="Open a new tab"
        aria-describedby={newTabDescriptionId}
      >
        <Plus size={16} aria-hidden="true" />
        <span id={newTabDescriptionId} className="sr-only">
          Opens a new browser tab
        </span>
      </Button>
      <Button
        size="icon"
        variant={incognitoMode ? "default" : "outline"}
        onClick={() => setIncognitoMode(!incognitoMode)}
        aria-pressed={incognitoMode}
        title={incognitoMode ? "Incognito mode on" : "Incognito mode off"}
        aria-label="Toggle incognito mode"
        aria-describedby={incognitoDescriptionId}
      >
        <EyeOff size={16} aria-hidden="true" />
        <span id={incognitoDescriptionId} className="sr-only">
          {incognitoMode ? "Incognito browsing enabled" : "Incognito browsing disabled"}
        </span>
      </Button>
    </div>
  );
}

function makeTabDomId(prefix: string, seed: string): string {
  const normalized = seed.replace(/[^a-zA-Z0-9_-]/g, "");
  return `${prefix}-${normalized || "tab"}`;
}
