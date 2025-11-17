"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AiPanel, type AiPanelTab } from "@/components/ai/AiPanel";
import { CommandPalette } from "@/components/command/CommandPalette";
import { ShellLayoutGrid } from "@/components/shell/ShellLayoutGrid";
import { SidebarNav } from "@/components/shell/SidebarNav";
import { TopBar } from "@/components/shell/TopBar";
import { ChatThreadProvider } from "@/lib/useChatThread";
import { NAV_ITEMS } from "@/lib/navigation";
import { useSessionPreference } from "@/hooks/useSessionPreference";
import { UI_SESSION_KEYS } from "@/lib/uiSession";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const router = useRouter();
  const [aiPanelOpen, setAiPanelOpen] = useSessionPreference(UI_SESSION_KEYS.aiPanelOpen, true);
  const [aiPanelTab, setAiPanelTab] = useSessionPreference<AiPanelTab>(UI_SESSION_KEYS.aiPanelTab, "chat");

  const toggleAiPanel = useCallback(() => {
    setAiPanelOpen((prev) => !prev);
  }, [setAiPanelOpen]);

  useEffect(() => {
    function handleShellHotkeys(event: KeyboardEvent) {
      const isMeta = event.metaKey || event.ctrlKey;
      if (!isMeta) return;
      const key = event.key.toLowerCase();

      if (event.shiftKey && key === "a") {
        event.preventDefault();
        toggleAiPanel();
        return;
      }

      const number = Number(event.key);
      if (!Number.isNaN(number) && number >= 1 && number <= NAV_ITEMS.length) {
        event.preventDefault();
        const target = NAV_ITEMS[number - 1];
        if (target) {
          router.push(target.href);
        }
      }
    }

    window.addEventListener("keydown", handleShellHotkeys);
    return () => window.removeEventListener("keydown", handleShellHotkeys);
  }, [router, toggleAiPanel]);

  return (
    <ChatThreadProvider>
      <div className="flex h-full min-h-0 flex-col">
        <TopBar
          onCommandPalette={() => setCommandPaletteOpen(true)}
          aiPanelOpen={aiPanelOpen}
          onToggleAiPanel={toggleAiPanel}
        />
        <div className="flex flex-1 overflow-hidden bg-muted/10">
          <SidebarNav />
          <ShellLayoutGrid>{children}</ShellLayoutGrid>
          <AiPanel
            isOpen={aiPanelOpen}
            activeTab={aiPanelTab}
            onTabChange={(tab) => setAiPanelTab(tab)}
            onOpen={() => setAiPanelOpen(true)}
            onClose={() => setAiPanelOpen(false)}
          />
        </div>
      </div>
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />
    </ChatThreadProvider>
  );
}
