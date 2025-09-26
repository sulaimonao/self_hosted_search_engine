"use client";

import { useCallback, useEffect, useState } from "react";
import { Command } from "cmdk";
import { CirclePlus, Loader2, Settings, Wand2 } from "lucide-react";
import { Dialog, DialogContent } from "@/components/dialog";

interface CommandPaletteProps {
  onAction: (command: string) => void;
  loading?: boolean;
}

export function CommandPalette({ onAction, loading }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  const handleKey = useCallback((event: KeyboardEvent) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      setOpen((value) => !value);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [handleKey]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="overflow-hidden border-none p-0 shadow-xl">
        <Command label="Command menu" shouldFilter={false} className="rounded-lg bg-background text-foreground">
          <div className="flex items-center gap-2 border-b border-border/40 px-3">
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Ask the agent what to do..."
              className="h-12 flex-1 border-none bg-transparent text-sm outline-none"
            />
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>
          <Command.List className="max-h-72 overflow-y-auto p-2 text-sm">
            <Command.Empty className="px-2 py-4 text-muted-foreground">
              {query ? "No matching commands." : "Try 'start crawl' or 'open settings'."}
            </Command.Empty>
            <Command.Group heading="Quick actions" className="space-y-2 text-xs uppercase tracking-wide text-muted-foreground">
              <Command.Item
                onSelect={() => {
                  onAction("start crawl");
                  setOpen(false);
                }}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground data-[selected=true]:bg-accent"
              >
                <CirclePlus className="h-4 w-4" /> Start crawl
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onAction("open settings");
                  setOpen(false);
                }}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground data-[selected=true]:bg-accent"
              >
                <Settings className="h-4 w-4" /> Open settings
              </Command.Item>
              <Command.Item
                onSelect={() => {
                  onAction("explain plan");
                  setOpen(false);
                }}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground data-[selected=true]:bg-accent"
              >
                <Wand2 className="h-4 w-4" /> Explain the next best action
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
