"use client";

import { EyeOff, Plus, X } from "lucide-react";
import { useMemo } from "react";
import { useShallow } from "zustand/react/shallow";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/state/useAppStore";

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

  return (
    <div className="flex items-center gap-2">
      <div className="max-w-full overflow-x-auto">
        <div className="flex items-center gap-2 py-1">
          {sorted.map((tab) => {
            const active = resolvedActiveTabId === tab.id;
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
              >
                {tab.favicon ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={tab.favicon} alt="" className="h-3 w-3" />
                ) : null}
                {tab.incognito ? <EyeOff size={12} className="h-3 w-3 text-muted-foreground" /> : null}
                <span className="max-w-[200px] truncate">{tab.title || tab.url || "New Tab"}</span>
                {tabs.length > 1 ? (
                  <X
                    size={14}
                    className="shrink-0 cursor-pointer opacity-60 hover:opacity-100"
                    onClick={(event) => {
                      event.stopPropagation();
                      closeTab(tab.id);
                    }}
                  />
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      <Button size="icon" variant="outline" onClick={() => addTab("https://example.com")} title="New tab">
        <Plus size={16} />
      </Button>
      <Button
        size="icon"
        variant={incognitoMode ? "default" : "outline"}
        onClick={() => setIncognitoMode(!incognitoMode)}
        aria-pressed={incognitoMode}
        title={incognitoMode ? "Incognito mode on" : "Incognito mode off"}
      >
        <EyeOff size={16} />
      </Button>
    </div>
  );
}
