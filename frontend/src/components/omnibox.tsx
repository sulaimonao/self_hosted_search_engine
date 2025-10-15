"use client";

import { forwardRef, useState } from "react";
import { Globe, Search, Settings, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

interface OmniBoxProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onOpenSettings: () => void;
  onOpenCommand: () => void;
  className?: string;
}

export const OmniBox = forwardRef<HTMLInputElement, OmniBoxProps>(
  ({ value, onChange, onSubmit, onOpenSettings, onOpenCommand, className }, ref) => {
    const [isFocused, setIsFocused] = useState(false);

    return (
      <div
        className={cn(
          "flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/95 p-4 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-card/80",
          className,
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Wand2 className="h-4 w-4" />
            <span>Desktop workspace</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onOpenCommand}
              className="rounded border px-2 py-1 font-mono"
            >
              ⌘K
            </button>
            <button type="button" className="rounded border px-2 py-1 font-mono">
              ⌘L
            </button>
          </div>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(value.trim());
          }}
          className="flex items-center gap-2 rounded-xl border border-border/60 bg-background/60 px-3 py-2 shadow-inner transition focus-within:border-primary"
        >
          <Search className="h-4 w-4 text-muted-foreground" />
          <Input
            ref={ref}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => setIsFocused(false)}
            placeholder="Paste a URL or ask the agent to search…"
            className="border-0 bg-transparent text-sm focus-visible:ring-0"
          />
          <Separator orientation="vertical" className="h-6" />
          <Button type="submit" size="sm" className="gap-1">
            <Globe className="h-4 w-4" /> Go
          </Button>
          <Button type="button" variant="ghost" size="icon" onClick={onOpenSettings}>
            <Settings className="h-4 w-4" />
          </Button>
        </form>
        {isFocused ? (
          <p className="text-xs text-muted-foreground">
            Enter a URL to load it in the preview, or type a keyword to start a guided search.
          </p>
        ) : null}
      </div>
    );
  }
);

OmniBox.displayName = "OmniBox";
