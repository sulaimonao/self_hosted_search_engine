"use client";

import { useState } from "react";

import { AiPanel } from "@/components/ai/AiPanel";
import { CommandPalette } from "@/components/command/CommandPalette";
import { ShellLayoutGrid } from "@/components/shell/ShellLayoutGrid";
import { SidebarNav } from "@/components/shell/SidebarNav";
import { TopBar } from "@/components/shell/TopBar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);

  return (
    <>
      <div className="flex h-full min-h-0 flex-col">
        <TopBar onCommandPalette={() => setCommandPaletteOpen(true)} />
        <div className="flex flex-1 overflow-hidden bg-muted/10">
          <SidebarNav />
          <ShellLayoutGrid>{children}</ShellLayoutGrid>
          <AiPanel />
        </div>
      </div>
      <CommandPalette open={commandPaletteOpen} onOpenChange={setCommandPaletteOpen} />
    </>
  );
}
