"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Globe2, Loader2, RefreshCw } from "lucide-react";

import { fetchDomainGraph, fetchDomainSnapshot } from "@/lib/api";
import type { DomainGraphResponse, DomainSnapshot } from "@/lib/types";
import { useAppStore } from "@/state/useAppStore";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";

const REFRESH_INTERVAL_MS = 15000;

function normalizeHost(value: string | undefined | null): string {
  if (!value) return "";
  return value.trim().toLowerCase();
}

function toHost(url: string | undefined | null): string {
  if (!url) return "";
  try {
    const parsed = new URL(url);
    const host = parsed.hostname || "";
    return host.replace(/^www\./i, "").toLowerCase();
  } catch {
    return "";
  }
}

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0";
  }
  return new Intl.NumberFormat().format(value);
}

function formatTimestamp(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  const ms = value > 1e12 ? value : value * 1000;
  try {
    return new Date(ms).toLocaleString();
  } catch {
    return "—";
  }
}

function formatRelative(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  const ms = value > 1e12 ? value : value * 1000;
  const delta = Date.now() - ms;
  if (!Number.isFinite(delta)) {
    return "—";
  }
  if (delta < 45 * 1000) {
    return "just now";
  }
  const minutes = Math.round(delta / 60000);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours}h ago`;
  }
  const days = Math.round(hours / 24);
  if (days < 14) {
    return `${days}d ago`;
  }
  return new Date(ms).toLocaleDateString();
}

type DomainStatsPanelProps = {
  defaultHost?: string | null;
  className?: string;
};

type ChartDatum = {
  day: string;
  pagesDelta: number;
  edgesDelta: number;
  pagesTotal: number;
  edgesTotal: number;
  bytesDelta: number;
};

export function DomainStatsPanel({ defaultHost, className }: DomainStatsPanelProps) {
  const { activeTab } = useAppStore(({ activeTab: current }) => ({ activeTab: current?.() }));
  const activeHost = useMemo(() => toHost(activeTab?.url), [activeTab?.url]);
  const normalizedDefaultHost = useMemo(() => normalizeHost(defaultHost), [defaultHost]);
  const defaultAppliedRef = useRef(false);

  const [followActiveTab, setFollowActiveTab] = useState(() => normalizedDefaultHost.length === 0);
  const [hostInput, setHostInput] = useState(() => normalizedDefaultHost);
  const [host, setHost] = useState(() => normalizedDefaultHost);
  const [snapshot, setSnapshot] = useState<DomainSnapshot | null>(null);
  const [graph, setGraph] = useState<DomainGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const handleFollowToggle = useCallback(
    (checked: boolean) => {
      setFollowActiveTab((prev) => {
        if (prev === checked) {
          return prev;
        }
        if (checked) {
          const next = normalizeHost(activeHost);
          if (next || next === "") {
            setHost((current) => (current === next ? current : next));
            setHostInput((current) => (current === next ? current : next));
          }
        }
        return checked;
      });
    },
    [activeHost],
  );

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (defaultAppliedRef.current) {
      return;
    }
    if (!normalizedDefaultHost) {
      return;
    }
    defaultAppliedRef.current = true;
    setFollowActiveTab(false);
    setHost(normalizedDefaultHost);
    setHostInput(normalizedDefaultHost);
  }, [normalizedDefaultHost]);

  useEffect(() => {
    if (!followActiveTab) {
      return;
    }
    const next = normalizeHost(activeHost);
    setHost((current) => (current === next ? current : next));
    setHostInput((current) => (current === next ? current : next));
  }, [followActiveTab, activeHost]);

  const loadData = useCallback(
    async (targetHost: string, options: { background?: boolean } = {}) => {
      const trimmed = targetHost.trim();
      if (!trimmed) {
        return;
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      if (options.background) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      try {
        const [snapshotData, graphData] = await Promise.all([
          fetchDomainSnapshot(trimmed, { signal: controller.signal }),
          fetchDomainGraph(trimmed, { signal: controller.signal, limit: 250 }),
        ]);
        if (controller.signal.aborted) {
          return;
        }
        setSnapshot(snapshotData);
        setGraph(graphData);
        setError(null);
      } catch (thrown) {
        if (controller.signal.aborted) {
          return;
        }
        const message = thrown instanceof Error ? thrown.message : String(thrown ?? "Unable to load domain stats");
        setError(message);
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!host) {
      setSnapshot(null);
      setGraph(null);
      setError(followActiveTab ? "Open a page in the browser to populate stats." : "Enter a host to visualize.");
      setLoading(false);
      setRefreshing(false);
      return;
    }
    setError(null);
    void loadData(host);
  }, [host, followActiveTab, loadData]);

  useEffect(() => {
    if (!host) {
      return;
    }
    const id = window.setInterval(() => {
      void loadData(host, { background: true });
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [host, loadData]);

  const chartData = useMemo<ChartDatum[]>(() => {
    if (!graph?.timeseries?.length) {
      return [];
    }
    const sorted = [...graph.timeseries].sort((a, b) => a.day.localeCompare(b.day));
    let pagesTotal = 0;
    let edgesTotal = 0;
    return sorted.map((entry) => {
      pagesTotal += entry.pages_delta ?? 0;
      edgesTotal += entry.edges_delta ?? 0;
      return {
        day: entry.day,
        pagesDelta: entry.pages_delta ?? 0,
        edgesDelta: entry.edges_delta ?? 0,
        pagesTotal,
        edgesTotal,
        bytesDelta: entry.bytes_delta ?? 0,
      };
    });
  }, [graph?.timeseries]);

  const topPages = snapshot?.top_pages ?? [];
  const queueEntries = snapshot?.queue_entries ?? [];
  const recentPages = snapshot?.recent ?? [];
  const keyTerms = snapshot?.key_terms ?? [];
  const kpis = snapshot?.kpis ?? null;
  const nodesCount = graph?.nodes?.length ?? 0;

  const busy = loading || refreshing;

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = normalizeHost(hostInput);
      setHostInput(trimmed);
      if (!trimmed) {
        setHost("");
        return;
      }
      setFollowActiveTab(false);
      setHost((current) => (current === trimmed ? current : trimmed));
    },
    [hostInput],
  );

  const handleRefresh = useCallback(() => {
    if (!host) {
      return;
    }
    void loadData(host);
  }, [host, loadData]);

  const isReady = snapshot?.found ?? false;

  return (
    <div className={className ? `flex h-full flex-col gap-4 ${className}` : "flex h-full flex-col gap-4"}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-md border bg-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <Globe2 className="h-4 w-4 text-muted-foreground" />
            <Input
              value={hostInput}
              onChange={(event) => setHostInput(event.target.value)}
              placeholder="example.com"
              className="flex-1"
            />
          </div>
          <Button type="submit" variant="secondary" disabled={busy && !refreshing}>
            {loading ? <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Loading</span> : "Inspect"}
          </Button>
          <Button type="button" variant="outline" onClick={handleRefresh} disabled={!host || busy}>
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
          <label className="inline-flex items-center gap-2">
            <Switch checked={followActiveTab} onCheckedChange={handleFollowToggle} id="follow-active-tab" />
            <span>Follow active browser tab</span>
          </label>
          {busy ? <span className="inline-flex items-center gap-2"><Loader2 className="h-3 w-3 animate-spin" /> Updating…</span> : null}
        </div>
      </form>

      {error ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Pages indexed</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold text-foreground">{formatNumber(kpis?.pages)}</p>
            <p className="text-xs text-muted-foreground">Nodes sampled: {formatNumber(nodesCount)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Edges discovered</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold text-foreground">{formatNumber(kpis?.edges)}</p>
            <p className="text-xs text-muted-foreground">Last seen {formatRelative(kpis?.last_seen)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Crawl queue</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold text-foreground">{formatNumber(kpis?.queue)}</p>
            <p className="text-xs text-muted-foreground">Oldest item {queueEntries[0]?.enqueued_at ? formatRelative(queueEntries[0]?.enqueued_at ?? null) : "—"}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">First seen</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-semibold text-foreground">{formatTimestamp(kpis?.first_seen)}</p>
            <p className="text-xs text-muted-foreground">Domain: {host || "—"}</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr,1fr]">
        <Card className="h-[320px]">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Capture trend (last 30 days)</CardTitle>
          </CardHeader>
          <CardContent className="h-full">
            {chartData.length ? (
              <div className="h-[260px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ left: 0, right: 12, top: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis dataKey="day" fontSize={12} tickLine={false} axisLine={{ stroke: "hsl(var(--border))" }} />
                    <YAxis fontSize={12} tickLine={false} axisLine={{ stroke: "hsl(var(--border))" }} allowDecimals={false} />
                    <Tooltip
                      formatter={(value: number, key) => {
                        if (key === "pagesTotal") return [formatNumber(value), "Pages (cumulative)"];
                        if (key === "edgesTotal") return [formatNumber(value), "Edges (cumulative)"];
                        if (key === "pagesDelta") return [formatNumber(value), "Pages (daily)"];
                        if (key === "edgesDelta") return [formatNumber(value), "Edges (daily)"];
                        if (key === "bytesDelta") return [formatNumber(value), "Bytes (daily)"];
                        return [formatNumber(value), key];
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area type="monotone" dataKey="pagesTotal" name="Pages" stroke="#2563eb" fill="rgba(37,99,235,0.25)" strokeWidth={2} />
                    <Area type="monotone" dataKey="edgesTotal" name="Edges" stroke="#10b981" fill="rgba(16,185,129,0.25)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                {isReady ? "No trend data yet—ingest more samples to populate the chart." : "Waiting for first sample."}
              </div>
            )}
          </CardContent>
        </Card>
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Key terms</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {keyTerms.length ? keyTerms.map((term) => (
                <Badge key={term} variant="secondary" className="text-xs uppercase tracking-wide">
                  {term}
                </Badge>
              )) : <p className="text-sm text-muted-foreground">No key terms extracted yet.</p>}
            </CardContent>
          </Card>
          <Card className="flex-1">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Crawl queue</CardTitle>
            </CardHeader>
            <CardContent className="h-full">
              {queueEntries.length ? (
                <ScrollArea className="h-[150px] pr-2">
                  <ul className="space-y-2 text-sm">
                    {queueEntries.map((entry) => (
                      <li key={`${entry.url}-${entry.priority}`} className="rounded border bg-muted/40 p-2">
                        <p className="truncate font-medium text-foreground" title={entry.url}>
                          {entry.url}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Priority {Number.isFinite(entry.priority) ? entry.priority.toFixed(2) : String(entry.priority)} · Attempts {entry.attempts} · {formatRelative(entry.enqueued_at)}
                        </p>
                        {entry.status ? (
                          <p className="text-xs text-muted-foreground">Status: {entry.status}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </ScrollArea>
              ) : (
                <p className="text-sm text-muted-foreground">Queue empty.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex h-[280px] flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Top pages</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            {topPages.length ? (
              <ScrollArea className="h-full pr-3">
                <ul className="space-y-3 text-sm">
                  {topPages.map((page, index) => (
                    <li key={page.url ?? String(page.id ?? index)} className="rounded border bg-muted/40 p-3">
                      <p className="font-medium text-foreground" title={page.url ?? undefined}>
                        {page.title || page.url || "Untitled"}
                      </p>
                      {page.url ? (
                        <p className="truncate text-xs text-muted-foreground">{page.url}</p>
                      ) : null}
                      <p className="text-xs text-muted-foreground">
                        {page.tokens ? `${formatNumber(page.tokens)} tokens · ` : null}
                        {page.word_count ? `${formatNumber(page.word_count)} words · ` : null}
                        Seen {formatRelative(page.last_seen)}
                      </p>
                      {page.status ? (
                        <p className="text-xs text-muted-foreground">Status: {page.status}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No samples captured yet.
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="flex h-[280px] flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Recent captures</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 overflow-hidden">
            {recentPages.length ? (
              <ScrollArea className="h-full pr-3">
                <ul className="space-y-3 text-sm">
                  {recentPages.map((entry) => (
                    <li key={`${entry.url}-${entry.last_seen}`} className="rounded border bg-muted/40 p-3">
                      <p className="font-medium text-foreground" title={entry.url}>
                        {entry.title || entry.url || "Untitled"}
                      </p>
                      {entry.url ? (
                        <p className="truncate text-xs text-muted-foreground">{entry.url}</p>
                      ) : null}
                      <p className="text-xs text-muted-foreground">Seen {formatRelative(entry.last_seen)}</p>
                      {entry.status ? (
                        <p className="text-xs text-muted-foreground">Status: {entry.status}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </ScrollArea>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Waiting for recent captures.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
