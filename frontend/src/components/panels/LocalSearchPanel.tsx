"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useBrowserNavigation } from "@/hooks/useBrowserNavigation";
import { searchIndex } from "@/lib/api";
import type { SearchHit, SearchResponseStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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

  const abortRef = useRef<AbortController | null>(null);
  const navigate = useBrowserNavigation();

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
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
              {hits.map((hit) => (
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
                    {hit.snippet ? (
                      <p className="mt-2 text-sm text-foreground/80">{hit.snippet}</p>
                    ) : null}
                  </button>
                </li>
              ))}
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
