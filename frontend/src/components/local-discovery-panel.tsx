"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import type { DiscoveryPreview } from "@/lib/types";
import { formatFileSize } from "@/lib/format";

// Candidate legacy component: the floating local discovery toaster is not referenced by current routes.
interface LocalDiscoveryPanelProps {
  items: DiscoveryPreview[];
  busyIds: Set<string>;
  onInclude: (id: string) => void;
  onDismiss: (id: string) => void;
}

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  const date = new Date(seconds * 1000);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function LocalDiscoveryPanel({ items, busyIds, onInclude, onDismiss }: LocalDiscoveryPanelProps) {
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => b.createdAt - a.createdAt);
  }, [items]);

  if (sorted.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex w-96 max-w-full flex-col gap-3">
      {sorted.map((item) => {
        const busy = busyIds.has(item.id);
        const detectedAt = formatTimestamp(item.createdAt);
        return (
          <div
            key={item.id}
            className="pointer-events-auto space-y-3 rounded-md border border-foreground/15 bg-background/95 p-4 shadow-lg"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-2 text-sm">
                <div className="space-y-1">
                  <p className="font-medium">Found file: {item.name}</p>
                  <p className="break-words text-xs text-muted-foreground">{item.path}</p>
                </div>
                <p className="text-xs text-muted-foreground">
                  {item.ext.toUpperCase()} · {formatFileSize(item.size)}
                  {detectedAt ? ` · Detected ${detectedAt}` : ""}
                </p>
                {item.preview ? (
                  <p className="line-clamp-3 text-xs text-muted-foreground">{item.preview}</p>
                ) : (
                  <p className="text-xs text-muted-foreground">Text extracted and ready to index.</p>
                )}
              </div>
              <div className="flex flex-col gap-2 text-xs">
                <Button size="sm" onClick={() => onInclude(item.id)} disabled={busy}>
                  {busy ? "Including…" : "Include"}
                </Button>
                <button
                  type="button"
                  className="text-muted-foreground transition hover:text-foreground"
                  onClick={() => onDismiss(item.id)}
                  disabled={busy}
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
