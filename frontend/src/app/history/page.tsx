"use client";

import { useEffect } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

import { Button } from "@/components/ui/button";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";
import { useAppStore } from "@/state/useAppStore";

export default function HistoryPage() {
  const history = useBrowserRuntimeStore((state) => state.history);
  const setHistory = useBrowserRuntimeStore((state) => state.setHistory);
  const activeTabId = useAppStore((state) => state.activeTabId ?? state.tabs[0]?.id);

  useEffect(() => {
    const api = resolveBrowserAPI();
    if (!api) {
      return;
    }
    let cancelled = false;
    api
      .requestHistory(200)
      .then((entries) => {
        if (!cancelled && entries) {
          setHistory(entries);
        }
      })
      .catch((error) => console.warn("[browser] failed to refresh history", error));
    return () => {
      cancelled = true;
    };
  }, [setHistory]);

  const api = resolveBrowserAPI();

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">History</h1>
          <p className="text-sm text-muted-foreground">Recently visited sites in this browser.</p>
        </div>
        <Link href="/">
          <Button variant="outline">Back to browser</Button>
        </Link>
      </header>
      <div className="space-y-3">
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No browsing history recorded yet.</p>
        ) : (
          history.map((entry) => (
            <div key={entry.id} className="flex items-center justify-between gap-4 rounded-md border p-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{entry.title || entry.url}</p>
                <p className="text-xs text-muted-foreground">
                  {entry.url}
                  {entry.visitTime
                    ? ` · ${formatDistanceToNow(entry.visitTime, { addSuffix: true })}`
                    : null}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    if (!api) return;
                    api.navigate(entry.url, { tabId: activeTabId ?? undefined, transition: "typed" });
                  }}
                >
                  Open
                </Button>
                <a href={entry.url} target="_blank" rel="noreferrer" className="text-xs text-muted-foreground">
                  View
                </a>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
