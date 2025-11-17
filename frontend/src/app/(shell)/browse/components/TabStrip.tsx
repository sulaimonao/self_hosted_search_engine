"use client";

import { useState } from "react";
import { PlusIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

const initialTabs = [
  { id: "tab-1", title: "Docs", url: "https://docs.local" },
  { id: "tab-2", title: "HydraFlow", url: "https://hydra" },
];

export function TabStrip() {
  const [tabs, setTabs] = useState(initialTabs);
  const [activeId, setActiveId] = useState(initialTabs[0]?.id ?? "");

  function addTab() {
    const id = `tab-${tabs.length + 1}`;
    const next = { id, title: `New Tab ${tabs.length + 1}`, url: "about:blank" };
    setTabs([...tabs, next]);
    setActiveId(id);
  }

  function closeTab(id: string) {
    const nextTabs = tabs.filter((tab) => tab.id !== id);
    setTabs(nextTabs);
    if (activeId === id && nextTabs.length) {
      setActiveId(nextTabs[0].id);
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-xl border bg-background px-3 py-2">
      <div className="flex flex-1 items-center gap-2 overflow-x-auto">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            className={`flex items-center gap-2 rounded-full px-3 py-1 text-sm ${
              tab.id === activeId
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground"
            }`}
          >
            <button type="button" onClick={() => setActiveId(tab.id)} className="flex-1 text-left">
              {tab.title}
            </button>
            <button type="button" onClick={() => closeTab(tab.id)} className="text-xs">
              <XIcon className="size-3" />
            </button>
          </div>
        ))}
      </div>
      <Button variant="ghost" size="icon" onClick={addTab}>
        <PlusIcon className="size-4" />
      </Button>
    </div>
  );
}
