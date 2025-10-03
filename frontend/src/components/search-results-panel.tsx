"use client";

import { AlertTriangle, ArrowUpRight, Loader2, RefreshCcw, Search as SearchIcon } from "lucide-react";
import { FormEvent, useMemo } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import type { SearchHit } from "@/lib/types";

const LOADING_PLACEHOLDERS = [0, 1, 2, 3];

type SearchResultsStatus = "idle" | "loading" | "ok" | "warming" | "focused_crawl_running" | "error";

interface SearchResultsPanelProps {
  className?: string;
  query: string;
  hits: SearchHit[];
  status: SearchResultsStatus;
  isLoading: boolean;
  error?: string | null;
  detail?: string | null;
  onOpenHit: (url: string) => void;
  onAskAgent?: (query: string) => void;
  onRefresh?: () => void;
  onQueryChange?: (value: string) => void;
  onSubmitQuery?: (value: string) => void;
  inputDisabled?: boolean;
  currentUrl?: string | null;
  confidence?: number | null;
  llmUsed?: boolean;
  triggerReason?: string | null;
  seedCount?: number | null;
  jobId?: string | null;
  lastFetchedAt?: string | null;
  actionLabel?: string | null;
  code?: string | null;
  candidates?: Array<Record<string, unknown>>;
}

function formatConfidence(confidence: number | null | undefined): number | null {
  if (typeof confidence !== "number" || Number.isNaN(confidence)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(confidence * 100)));
}

function normalizeReason(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return reason.replace(/_/g, " ");
}

export function SearchResultsPanel({
  className,
  query,
  hits,
  status,
  isLoading,
  error,
  detail,
  onOpenHit,
  onAskAgent,
  onRefresh,
  onQueryChange,
  onSubmitQuery,
  inputDisabled = false,
  currentUrl,
  confidence,
  llmUsed,
  triggerReason,
  seedCount,
  jobId,
  lastFetchedAt,
  actionLabel,
  code,
  candidates,
}: SearchResultsPanelProps) {
  const normalizedConfidence = useMemo(() => formatConfidence(confidence), [confidence]);
  const triggerLabel = useMemo(() => normalizeReason(triggerReason), [triggerReason]);
  const hasQuery = query.trim().length > 0;

  const statusBadge = useMemo(() => {
    if (status === "loading") {
      return (
        <Badge variant="secondary" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> Searching…
        </Badge>
      );
    }
    if (status === "focused_crawl_running") {
      return <Badge variant="outline">Focused crawl running</Badge>;
    }
    if (status === "warming") {
      return <Badge variant="destructive">Embedding warming</Badge>;
    }
    if (status === "error") {
      return <Badge variant="destructive">Search error</Badge>;
    }
    if (llmUsed) {
      return <Badge variant="outline">LLM rerank</Badge>;
    }
    return null;
  }, [status, llmUsed]);

  return (
    <div className={cn("flex flex-col bg-background", className)}>
      <div className="flex items-start justify-between gap-2 border-b px-3 py-2">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2 text-xs uppercase text-muted-foreground">
            <SearchIcon className="h-3.5 w-3.5" />
            <span>Local search</span>
            {lastFetchedAt ? (
              <span className="lowercase">· Updated {new Date(lastFetchedAt).toLocaleTimeString()}</span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-sm font-semibold">
              {hasQuery ? query : "Type a query to search the index"}
            </h2>
            {statusBadge}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {onRefresh ? (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={onRefresh}
              disabled={!hasQuery || isLoading}
              aria-label="Refresh search results"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            </Button>
          ) : null}
          {onAskAgent ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onAskAgent(query)}
              disabled={!hasQuery || isLoading}
            >
              Ask agent
            </Button>
          ) : null}
        </div>
      </div>

      <form
        className="flex items-center gap-2 px-3 py-2"
        onSubmit={(event: FormEvent<HTMLFormElement>) => {
          event.preventDefault();
          onSubmitQuery?.(query);
        }}
      >
        <Input
          value={query}
          onChange={(event) => onQueryChange?.(event.target.value)}
          placeholder={
            inputDisabled ? "Crawl a domain to enable local search" : "Search indexed documents"
          }
          disabled={inputDisabled}
          className="h-8 text-sm"
        />
        <Button
          type="submit"
          size="sm"
          disabled={inputDisabled || isLoading || !query.trim()}
        >
          {isLoading ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <SearchIcon className="mr-1 h-4 w-4" />
          )}
          Search
        </Button>
      </form>

      {normalizedConfidence !== null ? (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">Confidence</span>
          <Progress value={normalizedConfidence} className="h-1.5 flex-1" />
          <span>{normalizedConfidence}%</span>
        </div>
      ) : null}

      {status === "focused_crawl_running" ? (
        <div className="space-y-1 border-b px-3 py-2 text-xs text-muted-foreground">
          <p>
            Focused crawl queued{jobId ? ` (job ${jobId})` : ""}
            {triggerLabel ? ` after ${triggerLabel}` : ""}.
          </p>
          {typeof seedCount === "number" ? (
            <p>{seedCount} frontier seeds dispatched for exploration.</p>
          ) : null}
        </div>
      ) : null}

      {status === "warming" ? (
        <div className="space-y-2 border-b px-3 py-2 text-xs text-muted-foreground">
          <p>{detail ?? "Embedding model is starting up."}</p>
          {code ? (
            <p className="font-mono text-[11px] text-foreground">{code}</p>
          ) : null}
          {actionLabel ? (
            <p className="font-mono text-[11px] text-foreground">{actionLabel}</p>
          ) : null}
          {candidates && candidates.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {candidates.map((candidate, index) => {
                const label = typeof candidate?.model === "string" ? candidate.model : `Option ${index + 1}`;
                return (
                  <Badge key={label} variant="secondary">
                    {label}
                  </Badge>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}

      {error && status !== "warming" ? (
        <div className="flex items-start gap-2 border-b px-3 py-2 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 h-4 w-4" />
          <div className="space-y-1">
            <p>{error}</p>
            {detail ? <p className="text-xs text-muted-foreground">{detail}</p> : null}
          </div>
        </div>
      ) : null}

      <div className="flex-1 overflow-hidden">
        {isLoading ? (
          <div className="space-y-3 p-3">
            {LOADING_PLACEHOLDERS.map((placeholder) => (
              <div key={placeholder} className="space-y-2 rounded border p-3">
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-5/6" />
              </div>
            ))}
          </div>
        ) : hits.length > 0 ? (
          <ScrollArea className="h-full">
            <div className="space-y-2 p-3">
              {hits.map((hit) => {
                const isActive = currentUrl && hit.url && currentUrl === hit.url;
                return (
                  <button
                    key={hit.id}
                    type="button"
                    onClick={() => hit.url && onOpenHit(hit.url)}
                    disabled={!hit.url}
                    className={cn(
                      "group w-full rounded-lg border bg-card px-3 py-2 text-left shadow-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      isActive
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/50 hover:bg-muted/60",
                      !hit.url && "cursor-not-allowed opacity-70"
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-foreground">{hit.title}</p>
                        {hit.snippet ? (
                          <p
                            className="line-clamp-2 text-xs text-muted-foreground"
                            dangerouslySetInnerHTML={{ __html: hit.snippet }}
                          />
                        ) : null}
                      </div>
                      {hit.url ? (
                        <ArrowUpRight className="mt-0.5 h-4 w-4 text-muted-foreground transition group-hover:text-foreground" />
                      ) : null}
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      {hit.url ? <span className="truncate font-mono text-[11px]">{hit.url}</span> : null}
                      {typeof hit.score === "number" ? (
                        <span>Score {hit.score.toFixed(2)}</span>
                      ) : null}
                      {typeof hit.blendedScore === "number" ? (
                        <span>Blend {hit.blendedScore.toFixed(2)}</span>
                      ) : null}
                      {hit.lang ? <span>Lang {hit.lang}</span> : null}
                    </div>
                  </button>
                );
              })}
            </div>
          </ScrollArea>
        ) : hasQuery ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
            <SearchIcon className="h-6 w-6" />
            <p>No results yet. Try refining your query or queue a crawl.</p>
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
            <SearchIcon className="h-6 w-6" />
            <p>Enter a keyword above to search your local index.</p>
          </div>
        )}
      </div>
    </div>
  );
}
