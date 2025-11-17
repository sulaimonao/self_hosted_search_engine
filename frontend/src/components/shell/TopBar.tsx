"use client";

import { BellIcon, CommandIcon, HelpCircleIcon, SparklesIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface TopBarProps {
  onCommandPalette: () => void;
  aiPanelOpen: boolean;
  onToggleAiPanel: () => void;
}

export function TopBar({ onCommandPalette, aiPanelOpen, onToggleAiPanel }: TopBarProps) {
  return (
    <header className="border-b border-border-subtle bg-app-elevated/95 text-fg backdrop-blur supports-[backdrop-filter]:bg-app-elevated/75">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-3 px-4">
        <div className="font-semibold tracking-tight text-fg">Self Hosted Copilot</div>
        <div className="hidden flex-1 items-center gap-2 rounded-xs border border-border-subtle bg-app-subtle/70 px-3 py-1 text-sm text-fg-muted lg:flex">
          <CommandIcon className="size-4" />
          <span>Type / to ask anything</span>
        </div>
        <div className="flex flex-1 items-center gap-3 lg:max-w-sm">
          <Input placeholder="Search everything..." className="bg-app-input" />
        </div>
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
