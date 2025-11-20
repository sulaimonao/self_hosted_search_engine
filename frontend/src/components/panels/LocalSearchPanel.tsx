"use client";

import { Info, Loader2, ShieldCheck, ShieldX } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useBrowserNavigation } from "@/hooks/useBrowserNavigation";
import { searchIndex, fetchShadowConfig, updateShadowConfig } from "@/lib/api";
import type { SearchHit, SearchResponseStatus, ShadowConfig } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { DomainStatsPanel } from "@/components/domain/DomainStatsPanel";

type PanelPhase = "idle" | "loading" | "ready" | "error";

export function LocalSearchPanel() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [phase, setPhase] = useState<PanelPhase>("idle");
  const [responseStatus, setResponseStatus] = useState<SearchResponseStatus | "idle">("idle");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [llmUsed, setLlmUsed] = useState(false);
  const [visualizationOpen, setVisualizationOpen] = useState(false);
  const [shadowConfig, setShadowConfig] = useState<ShadowConfig | null>(null);
  const [shadowLoading, setShadowLoading] = useState(false);
  const [shadowError, setShadowError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const abortRef = useRef<AbortController | null>(null);
  const navigate = useBrowserNavigation();

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    fetchShadowConfig()
      .then((config) => setShadowConfig(config))
      .catch((err) => setShadowError(err instanceof Error ? err.message : String(err)));
  }, []);

  const runSearch = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        setHits([]);
        setPhase("idle");
        setError(null);
        setWarning(null);
        setInfo(null);
        setResponseStatus("idle");
        setConfidence(null);
        setLlmUsed(false);
        setLastUpdated(null);
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setPhase("loading");
      setError(null);
      setWarning(null);
      setInfo(null);
      setResponseStatus("idle");
      setConfidence(null);
      setLlmUsed(false);
      setLastUpdated(null);

      try {
        const result = await searchIndex(trimmed, { limit: 20, signal: controller.signal });
        if (controller.signal.aborted) {
          return;
        }
        setHits(result.hits);
        setPhase("ready");
        setResponseStatus(result.status);
        setWarning(result.error ?? null);
        setInfo(result.detail ?? null);
        setConfidence(typeof result.confidence === "number" ? result.confidence : null);
        setLlmUsed(Boolean(result.llmUsed));
        setLastUpdated(new Date().toISOString());
      } catch (thrown) {
        if (controller.signal.aborted) {
          return;
        }
        const message = thrown instanceof Error ? thrown.message : String(thrown ?? "Search failed");
        setHits([]);
        setPhase("error");
        setError(message);
        setResponseStatus("idle");
        setConfidence(null);
        setLlmUsed(false);
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [],
  );

  const toggleShadowCapture = useCallback(
    async (enabled: boolean) => {
      setShadowLoading(true);
      setShadowError(null);
      try {
        const updated = await updateShadowConfig({ enabled });
        setShadowConfig(updated);
      } catch (thrown) {
        const message = thrown instanceof Error ? thrown.message : String(thrown ?? "Shadow toggle failed");
        setShadowError(message);
      } finally {
        setShadowLoading(false);
      }
    },
    [],
  );

  const toggleDetails = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      void runSearch(query);
    },
    [query, runSearch],
  );

  const handleResultClick = useCallback(
    (hit: SearchHit, event: React.MouseEvent<HTMLButtonElement>) => {
      const newTab = event.metaKey || event.ctrlKey;
      navigate(hit.url, { newTab, title: hit.title });
    },
    [navigate],
  );

  const statusLine = useMemo(() => {
    if (phase === "error" && error) {
      return { kind: "error" as const, text: error };
    }
    if (warning) {
      return { kind: "warning" as const, text: warning };
    }
    if (info) {
      return { kind: "info" as const, text: info };
    }
    if (responseStatus === "focused_crawl_running") {
      return { kind: "info" as const, text: "Focused crawl running to enrich these results." };
    }
    if (responseStatus === "warming") {
      return {
        kind: "info" as const,
        text: "Index warming up—retry in a moment if results look sparse.",
      };
    }
    if (phase === "ready" && hits.length === 0) {
      return {
        kind: "info" as const,
        text: "No results yet—try another query or crawl additional pages.",
      };
    }
    return null;
  }, [error, hits.length, info, phase, responseStatus, warning]);

  const statusClass =
    statusLine?.kind === "error"
      ? "text-destructive"
      : statusLine?.kind === "warning"
      ? "text-state-warning"
      : "text-muted-foreground";

  const metaLine = useMemo(() => {
    if (phase !== "ready") {
      return null;
    }
    const parts: string[] = [];
    if (typeof confidence === "number") {
      parts.push(`Confidence ${(confidence * 100).toFixed(0)}%`);
    }
    if (llmUsed) {
      parts.push("LLM rerank ✓");
    }
    if (lastUpdated) {
      try {
        parts.push(`Updated ${new Date(lastUpdated).toLocaleTimeString()}`);
      } catch {
        parts.push(`Updated just now`);
      }
    }
    if (!parts.length) {
      return null;
    }
    return parts.join(" · ");
  }, [confidence, lastUpdated, llmUsed, phase]);

  return (
    <div className="flex h-full w-[26rem] flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">Local search</h3>
          <p className="text-xs text-muted-foreground">Search the indexed document store.</p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setVisualizationOpen(true)}
        >
          Domain stats
        </Button>
      </div>
      <div className="flex items-center justify-between gap-3 rounded-md border border-border-subtle bg-muted/40 px-3 py-2 text-xs">
        <div className="flex items-center gap-2">
          {shadowConfig?.enabled ? (
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          ) : (
            <ShieldX className="h-4 w-4 text-muted-foreground" />
          )}
          <div>
            <p className="font-medium text-foreground">Record browsing</p>
            <p className="text-[11px] text-muted-foreground">
              Capture researcher browsing into the library when enabled.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {shadowLoading ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
          <Switch
            checked={shadowConfig?.enabled ?? false}
            onCheckedChange={(value) => void toggleShadowCapture(value)}
            disabled={shadowLoading}
            aria-label="Toggle recording browsing"
          />
        </div>
      </div>
      {shadowError ? (
        <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[11px] text-destructive">
          <Info className="h-3.5 w-3.5" />
          {shadowError}
        </div>
      ) : null}
      <form className="flex gap-2" onSubmit={handleSubmit}>
        <Input
          placeholder="Search indexed documents"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={phase === "loading"}
        />
        <Button type="submit" variant="secondary" disabled={phase === "loading" || !query.trim()}>
          {phase === "loading" ? (
            <span className="inline-flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Searching
            </span>
          ) : (
            "Search"
          )}
        </Button>
      </form>
      {statusLine ? <p className={`text-xs ${statusClass}`}>{statusLine.text}</p> : null}
      {metaLine ? (
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{metaLine}</p>
      ) : null}
      <div className="flex-1 overflow-hidden">
        {phase === "loading" ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>Querying local index…</span>
          </div>
        ) : hits.length > 0 ? (
          <ScrollArea className="h-full pr-3">
            <ul className="space-y-3">
              {hits.map((hit) => {
                const aboutRecord = (hit.about as Record<string, unknown> | null) ?? null;
                const weightsRaw =
                  aboutRecord && typeof aboutRecord === "object"
                    ? (aboutRecord["weights"] as Record<string, unknown> | undefined)
                    : null;
                const keywordWeight =
                  weightsRaw && typeof weightsRaw.keyword === "number" ? (weightsRaw.keyword as number) : null;
                const vectorWeight =
                  weightsRaw && typeof weightsRaw.vector === "number" ? (weightsRaw.vector as number) : null;
                return (
                  <li key={hit.id} className="rounded-lg border bg-card p-3 shadow-sm">
                    <button
                      type="button"
                      onClick={(event) => handleResultClick(hit, event)}
                      className="w-full text-left"
                      title={hit.url}
                    >
                      <p className="font-medium text-foreground hover:underline">
                        {hit.title || hit.url || "Untitled"}
                      </p>
                      {hit.url ? (
                        <p className="text-xs text-muted-foreground">{hit.url}</p>
                      ) : null}
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                        {hit.matchReason?.includes("semantic") ? (
                          <Badge variant="secondary" className="text-[11px]">
                            Semantic match
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[11px]">
                            Keyword
                          </Badge>
                        )}
                        {hit.source ? (
                          <Badge variant="outline" className="text-[11px] lowercase">
                            {hit.source}
                          </Badge>
                        ) : null}
                        {hit.domain ? <span>{hit.domain}</span> : null}
                        {typeof hit.temp === "boolean" ? (
                          <Badge variant={hit.temp ? "outline" : "secondary"} className="text-[11px]">
                            {hit.temp ? "Temporary" : "Saved to library"}
                          </Badge>
                        ) : null}
                      </div>
                      {hit.snippet ? (
                        <p
                          className="mt-2 text-sm text-foreground/80"
                          dangerouslySetInnerHTML={{ __html: hit.snippet }}
                        />
                      ) : null}
                    </button>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      {typeof hit.keywordScore === "number" ? <span>BM25 {hit.keywordScore.toFixed(2)}</span> : null}
                      {typeof hit.vectorScore === "number" ? <span>Semantic {hit.vectorScore.toFixed(2)}</span> : null}
                      {typeof hit.blendedScore === "number" ? <span>Blend {hit.blendedScore.toFixed(2)}</span> : null}
                      <Button
                        type="button"
                        size="xs"
                        variant="ghost"
                        onClick={() => toggleDetails(hit.id)}
                      >
                        {expanded.has(hit.id) ? "Hide details" : "About this result"}
                      </Button>
                    </div>
                    {expanded.has(hit.id) ? (
                      <div className="mt-2 space-y-1 rounded-md border border-border-subtle bg-muted/50 p-2 text-[11px] text-muted-foreground">
                        <p>
                          Why: {hit.matchReason ?? "keyword"} • Domain {hit.domain ?? "unknown"}
                        </p>
                        {keywordWeight !== null || vectorWeight !== null ? (
                          <p>
                            Weights {keywordWeight !== null ? `k=${keywordWeight.toFixed(2)}` : ""}{" "}
                            {vectorWeight !== null ? `v=${vectorWeight.toFixed(2)}` : ""}
                          </p>
                        ) : null}
                        {hit.temp !== undefined ? (
                          <p>{hit.temp ? "Not stored permanently until saved." : "In library for future queries."}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </ScrollArea>
        ) : (
          <div className="flex h-full flex-col items-center justify-center rounded-md border border-dashed text-center text-xs text-muted-foreground">
            <div className="px-6">
              {phase === "idle"
                ? "Enter a query to search the local index."
                : "No matches yet. Try broadening your search."}
            </div>
          </div>
        )}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Tip: Hold ⌘/Ctrl while clicking a result to open it in a new tab.
      </p>

      <Dialog open={visualizationOpen} onOpenChange={setVisualizationOpen}>
        <DialogContent className="max-w-[92vw] gap-0 overflow-hidden p-0 sm:max-w-[1100px]">
          <DialogHeader>
            <DialogTitle>Domain stats</DialogTitle>
          </DialogHeader>
          <div className="max-h-[78vh] overflow-y-auto px-6 pb-6">
            <DomainStatsPanel className="min-h-[65vh]" />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
