"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import { Button } from "@/components/ui/button";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";
import { useAppStore } from "@/state/useAppStore";
import { apiClient } from "@/lib/backend/apiClient";

type HistoryItem = {
  id: number;
  url: string;
  title?: string | null;
  visited_at?: string | null;
  referrer?: string | null;
  tab_id?: string | null;
};

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const setRuntimeHistory = useBrowserRuntimeStore((state) => state.setHistory);
  const activeTabId = useAppStore((state) => state.activeTabId ?? state.tabs[0]?.id);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const payload = await apiClient.get<{ items: HistoryItem[] }>("/api/history/list?limit=200");
        if (!cancelled) {
          setItems(payload.items ?? []);
          // keep runtime store in sync for components still using it
          setRuntimeHistory(
            (payload.items ?? []).map((entry) => ({
              id: entry.id,
              url: entry.url,
              title: entry.title ?? entry.url,
              visitTime: entry.visited_at ? new Date(entry.visited_at).getTime() : Date.now(),
            })),
          );
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Unable to load history";
          setError(message);
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
  }, [setRuntimeHistory]);

  const api = resolveBrowserAPI();
  const historyList = useMemo(() => items, [items]);

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">History</h1>
          <p className="text-sm text-muted-foreground">Recently visited sites in this browser.</p>
        </div>
        <Link href="/browser">
          <Button variant="outline">Back to browser</Button>
        </Link>
      </header>
      {error ? (
        <div className="rounded-md border border-destructive/60 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      <div className="space-y-3">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading history…</p>
        ) : historyList.length === 0 ? (
          <p className="text-sm text-muted-foreground">No browsing history recorded yet.</p>
        ) : (
          historyList.map((entry) => {
            const visited = entry.visited_at ? new Date(entry.visited_at).getTime() : null;
            return (
              <div key={entry.id} className="flex items-center justify-between gap-4 rounded-md border p-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{entry.title || entry.url}</p>
                  <p className="text-xs text-muted-foreground">
                    {entry.url}
                    {visited ? ` · ${formatDistanceToNow(visited, { addSuffix: true })}` : null}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (api) {
                        api.navigate(entry.url, { tabId: activeTabId ?? undefined, transition: "typed" });
                      } else {
                        window.open(entry.url, "_blank", "noreferrer");
                      }
                    }}
                  >
                    Open
                  </Button>
                  <a href={entry.url} target="_blank" rel="noreferrer" className="text-xs text-muted-foreground">
                    View
                  </a>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
