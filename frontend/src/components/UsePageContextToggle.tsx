"use client";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

interface ContextSummary {
  url?: string | null;
  selectionWordCount?: number | null;
}

interface UsePageContextToggleProps {
  enabled: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
  summary?: ContextSummary | null;
}

function extractHostname(url?: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}

export function UsePageContextToggle({ enabled, disabled = false, onChange, summary }: UsePageContextToggleProps) {
  const host = extractHostname(summary?.url);
  const selectionCount = summary?.selectionWordCount ?? null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Switch
        id="use-page-context"
        aria-label="Use current page context"
        checked={enabled}
        disabled={disabled}
        onCheckedChange={onChange}
        className="shrink-0"
      />
      <label
        htmlFor="use-page-context"
        className={cn("cursor-pointer select-none", disabled && "opacity-60")}
      >
        Use current page context
      </label>
      {enabled && (host || typeof selectionCount === "number") ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
          {host ? <span>{host}</span> : null}
          {host && typeof selectionCount === "number" ? <span>•</span> : null}
          {typeof selectionCount === "number" ? <span>{selectionCount} words</span> : null}
        </span>
      ) : null}
    </div>
  );
}
