"use client";

import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import { useAppStore } from "@/state/useAppStore";

type FallbackItem = {
  title: string;
  url: string;
};

type FallbackResponse = {
  strategy: string;
  url: string;
  title?: string;
  items: FallbackItem[];
  diagnostics?: string[];
};

export function AgentLogPanel() {
  const activeTab = useAppStore(useShallow((state) => state.activeTab?.()));
  const [fallback, setFallback] = useState<FallbackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = activeTab?.url;
    if (!url || typeof window === "undefined") {
      setFallback(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/browser/fallback?url=${encodeURIComponent(url)}`);
        if (!response.ok) {
          throw new Error(`status ${response.status}`);
        }
        const payload = (await response.json()) as FallbackResponse;
        if (!cancelled) {
          setFallback(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [activeTab?.url]);

  const strategyLabel = fallback?.strategy ? fallback.strategy.replace("_", " ") : "unknown";

  return (
    <div className="flex h-full w-[22rem] flex-col gap-3 p-4 text-sm">
      <div>
        <h3 className="text-sm font-semibold">Agent discovery</h3>
        <p className="text-xs text-muted-foreground">Fallback exploration for {activeTab?.url ?? "current tab"}</p>
      </div>
      <div className="flex-1 overflow-y-auto rounded border p-3 text-xs">
        {loading ? (
          <p className="text-muted-foreground">Fetching fallback suggestions…</p>
        ) : error ? (
          <p className="text-destructive">{error}</p>
        ) : fallback && fallback.items.length > 0 ? (
          <div className="space-y-2">
            <p className="font-semibold text-muted-foreground">Strategy: {strategyLabel}</p>
            <ul className="space-y-2">
              {fallback.items.slice(0, 12).map((item, index) => (
                <li key={`${item.url}:${index}`} className="rounded border border-border/50 bg-background/70 p-2">
                  <p className="font-medium text-foreground">{item.title || item.url}</p>
                  <p className="truncate text-[11px] text-muted-foreground">{item.url}</p>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-muted-foreground">No fallback suggestions available.</p>
        )}
      </div>
      {fallback?.diagnostics && fallback.diagnostics.length > 0 ? (
        <div className="rounded border border-dashed border-border/60 bg-muted/40 p-2 text-[11px] text-muted-foreground">
          Diagnostics: {fallback.diagnostics.join(", ")}
        </div>
      ) : null}
    </div>
  );
}
