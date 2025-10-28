"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";

type IndexStore = {
  name: string;
  count: number;
  ok: boolean;
  dimensions?: number | null;
};

type IndexHealthPayload = {
  status?: string;
  last_reindex?: number | null;
  rebuild_available?: boolean;
  stores?: IndexStore[];
};

interface IndexHealthPanelProps {
  onRefreshStatus?: (status: "green" | "yellow" | "red" | "unknown") => void;
}

export function IndexHealthPanel({ onRefreshStatus }: IndexHealthPanelProps) {
  const [data, setData] = useState<IndexHealthPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildMessage, setRebuildMessage] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/index/health");
      if (!response.ok) {
        throw new Error(`status ${response.status}`);
      }
      const payload = (await response.json()) as IndexHealthPayload;
      setData(payload);
      if (onRefreshStatus) {
        const status = (payload.status ?? "unknown") as "green" | "yellow" | "red" | "unknown";
        onRefreshStatus(["green", "yellow", "red"].includes(status) ? status : "unknown");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const lastReindex = useMemo(() => {
    if (!data?.last_reindex) {
      return null;
    }
    try {
      return new Date(data.last_reindex * 1000).toLocaleString();
    } catch {
      return null;
    }
  }, [data?.last_reindex]);

  const handleRebuild = async () => {
    setRebuilding(true);
    setRebuildMessage(null);
    try {
      const response = await fetch("/api/index/rebuild", { method: "POST", headers: { "Content-Type": "application/json" } });
      const payload = (await response.json()) as { accepted?: boolean };
      if (!response.ok || !payload.accepted) {
        throw new Error("Rebuild request failed");
      }
      setRebuildMessage("Rebuild started. Refresh to monitor progress.");
      await load();
    } catch (err) {
      setRebuildMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setRebuilding(false);
    }
  };

  const stores = data?.stores ?? [];

  return (
    <div className="space-y-3 text-sm">
      {error ? <p className="text-destructive">{error}</p> : null}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Status: {data?.status ?? "unknown"}</span>
        {lastReindex ? <span>Last reindex: {lastReindex}</span> : null}
      </div>
      <ScrollArea className="h-64 rounded border">
        <div className="space-y-2 p-3 text-xs">
          {stores.length === 0 ? (
            <p className="text-muted-foreground">No stores reported.</p>
          ) : (
            stores.map((store) => (
              <div
                key={store.name}
                className="rounded border border-border/60 bg-background/90 p-3 shadow-sm"
              >
                <div className="flex items-center justify-between font-semibold">
                  <span>{store.name}</span>
                  <span className={store.ok ? "text-emerald-600" : "text-destructive"}>
                    {store.ok ? "healthy" : "unavailable"}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-muted-foreground">
                  <span>Documents: {store.count ?? 0}</span>
                  {store.dimensions ? <span>Dimensions: {store.dimensions}</span> : null}
                </div>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
      <div className="flex items-center justify-between">
        <Button type="button" size="sm" variant="outline" onClick={() => load()} disabled={loading}>
          Refresh
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={() => void handleRebuild()}
          disabled={rebuilding || !data?.rebuild_available}
        >
          {rebuilding ? "Rebuilding…" : "Rebuild indexes"}
        </Button>
      </div>
      {rebuildMessage ? <p className="text-xs text-muted-foreground">{rebuildMessage}</p> : null}
    </div>
  );
}

export default IndexHealthPanel;
