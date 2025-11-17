"use client";

import { BellIcon, CommandIcon, HelpCircleIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function TopBar({ onCommandPalette }: { onCommandPalette: () => void }) {
  return (
    <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
        <div className="font-semibold tracking-tight">Self Hosted Copilot</div>
        <div className="hidden flex-1 items-center gap-2 rounded-full border px-3 py-1 text-sm text-muted-foreground lg:flex">
          <CommandIcon className="size-4" />
          <span>Type / to ask anything</span>
        </div>
        <div className="flex flex-1 items-center gap-3 lg:max-w-sm">
          <Input placeholder="Search everything..." className="bg-muted/50" />
        </div>
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
