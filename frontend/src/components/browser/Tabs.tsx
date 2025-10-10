"use client";

import { Plus, X } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/state/useAppStore";

export function TabsBar() {
  const tabs = useAppStore((state) => state.tabs);
  const activeTabId = useAppStore((state) => state.activeTabId ?? state.tabs[0]?.id);
  const setActive = useAppStore((state) => state.setActive);
  const closeTab = useAppStore((state) => state.closeTab);
  const addTab = useAppStore((state) => state.addTab);

  const sorted = useMemo(() => tabs, [tabs]);

  return (
    <div className="flex items-center gap-2">
      <div className="max-w-full overflow-x-auto">
        <div className="flex items-center gap-2 py-1">
          {sorted.map((tab) => {
            const active = activeTabId === tab.id;
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
      <Button size="icon" variant="outline" onClick={() => addTab("https://example.com")}
        title="New tab">
        <Plus size={16} />
      </Button>
    </div>
  );
}
