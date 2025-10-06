"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, Check, ChevronDown, ChevronUp, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import type { CrawlQueueItem, CrawlScope } from "@/lib/types";

interface CrawlManagerProps {
  queue: CrawlQueueItem[];
  defaultScope: CrawlScope;
  onAddUrl: (url: string, scope: CrawlScope, notes?: string) => Promise<void> | void;
  onRemove: (id: string) => Promise<void> | void;
  onUpdateScope: (id: string, scope: CrawlScope) => Promise<void> | void;
  onScopePresetChange?: (scope: CrawlScope) => void;
  onRefresh?: () => Promise<unknown>;
  isLoading?: boolean;
  errorMessage?: string | null;
  currentUrl?: string | null;
}

const SCOPE_LABEL: Record<CrawlScope, string> = {
  page: "This page",
  domain: "This domain",
  "allowed-list": "Allowed list",
  custom: "Custom scope",
};

interface CrawlSeedStats {
  lastCrawledAt: string | null;
  lastVisitedAt: string | null;
  lastIndexedAt: string | null;
  indexedDocuments: number | null;
  availableDocuments: number | null;
}

const TIMESTAMP_CANDIDATES: Record<keyof Omit<CrawlSeedStats, "indexedDocuments" | "availableDocuments">, string[]> = {
  lastCrawledAt: [
    "last_crawled_at",
    "lastCrawledAt",
    "last_crawl_at",
    "lastCrawlAt",
    "last_crawl",
    "lastCrawl",
  ],
  lastVisitedAt: [
    "last_visited_at",
    "lastVisitedAt",
    "last_visit_at",
    "lastVisitAt",
    "last_visit",
    "lastVisit",
  ],
  lastIndexedAt: [
    "last_indexed_at",
    "lastIndexedAt",
    "indexed_at",
    "indexedAt",
    "last_index",
    "lastIndex",
  ],
};

const NUMBER_CANDIDATES: Record<"indexedDocuments" | "availableDocuments", string[]> = {
  indexedDocuments: [
    "indexed_documents",
    "documents_indexed",
    "docs_indexed",
    "indexed",
    "documentsIndexed",
    "indexedDocs",
  ],
  availableDocuments: [
    "available_documents",
    "documents_available",
    "total_documents",
    "documents_total",
    "discovered_documents",
    "available",
    "documentsDiscovered",
    "totalDocs",
  ],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function enumerateNestedRecords(source: Record<string, unknown>): Record<string, unknown>[] {
  const queue: Record<string, unknown>[] = [source];
  const seen = new Set<Record<string, unknown>>();
  const results: Record<string, unknown>[] = [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (seen.has(current)) {
      continue;
    }
    seen.add(current);
    results.push(current);
    for (const value of Object.values(current)) {
      if (isRecord(value)) {
        queue.push(value);
      } else if (Array.isArray(value)) {
        for (const item of value) {
          if (isRecord(item)) {
            queue.push(item);
          }
        }
      }
    }
  }
  return results;
}

function findValue(source: Record<string, unknown> | undefined, keys: string[]): unknown {
  if (!source || keys.length === 0) {
    return undefined;
  }
  for (const record of enumerateNestedRecords(source)) {
    for (const key of keys) {
      if (key in record) {
        return record[key];
      }
    }
  }
  return undefined;
}

function coerceTimestamp(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    const candidate = value.trim();
    const parsed = new Date(candidate);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toISOString();
    }
  }
  return null;
}

function coerceNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

function extractSeedStats(extras?: Record<string, unknown>): CrawlSeedStats {
  if (!extras || !isRecord(extras)) {
    return {
      lastCrawledAt: null,
      lastVisitedAt: null,
      lastIndexedAt: null,
      indexedDocuments: null,
      availableDocuments: null,
    };
  }

  const stats: CrawlSeedStats = {
    lastCrawledAt: null,
    lastVisitedAt: null,
    lastIndexedAt: null,
    indexedDocuments: null,
    availableDocuments: null,
  };

  for (const [key, candidates] of Object.entries(TIMESTAMP_CANDIDATES)) {
    const raw = findValue(extras, candidates);
    const coerced = coerceTimestamp(raw);
    if (coerced) {
      stats[key as keyof typeof TIMESTAMP_CANDIDATES] = coerced;
    }
  }

  for (const [key, candidates] of Object.entries(NUMBER_CANDIDATES)) {
    const raw = findValue(extras, candidates);
    const coerced = coerceNumber(raw);
    if (coerced !== null) {
      stats[key as keyof typeof NUMBER_CANDIDATES] = coerced;
    }
  }

  return stats;
}

function safeHostname(url?: string | null): string | null {
  if (!url) {
    return null;
  }
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

interface TimestampParts {
  primary: string;
  secondary: string | null;
}

function formatTimestampParts(timestamp: string | null | undefined): TimestampParts {
  if (!timestamp) {
    return { primary: "Never", secondary: null };
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return { primary: "Unknown", secondary: null };
  }
  const absolute = date.toLocaleString();
  let relative: string | null = null;
  try {
    const diffMs = date.getTime() - Date.now();
    const minutes = diffMs / 60000;
    const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
    const absMinutes = Math.abs(minutes);
    if (absMinutes < 1) {
      relative = "Just now";
    } else if (absMinutes < 60) {
      relative = rtf.format(Math.round(minutes), "minute");
    } else {
      const hours = minutes / 60;
      const absHours = Math.abs(hours);
      if (absHours < 48) {
        relative = rtf.format(Math.round(hours), "hour");
      } else {
        const days = hours / 24;
        const absDays = Math.abs(days);
        if (absDays < 14) {
          relative = rtf.format(Math.round(days), "day");
        } else if (absDays < 56) {
          relative = rtf.format(Math.round(days / 7), "week");
        } else {
          const months = days / 30;
          relative = rtf.format(Math.round(months), "month");
        }
      }
    }
  } catch {
    relative = null;
  }
  if (relative) {
    return { primary: relative, secondary: absolute };
  }
  return { primary: absolute, secondary: null };
}

function formatCount(value: number | null | undefined): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat().format(value);
  }
  return "—";
}

function computeCoverage(indexed: number | null, total: number | null): string | null {
  if (
    typeof indexed !== "number" ||
    !Number.isFinite(indexed) ||
    typeof total !== "number" ||
    !Number.isFinite(total) ||
    total <= 0
  ) {
    return null;
  }
  const ratio = Math.min(100, Math.max(0, Math.round((indexed / total) * 100)));
  return `${ratio}% coverage`;
}

interface SummaryStatProps {
  label: string;
  value: string;
  detail?: string | null;
}

function SummaryStat({ label, value, detail }: SummaryStatProps) {
  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-base font-semibold text-foreground">{value}</p>
      {detail && <p className="text-[11px] text-muted-foreground">{detail}</p>}
    </div>
  );
}

function parseDroppedUrl(event: React.DragEvent<HTMLDivElement>) {
  const uri = event.dataTransfer.getData("text/uri-list");
  if (uri) return uri.trim();
  const text = event.dataTransfer.getData("text/plain");
  if (text.startsWith("http")) return text.trim();
  return "";
}

export function CrawlManager({
  queue,
  defaultScope,
  onAddUrl,
  onRemove,
  onUpdateScope,
  onScopePresetChange,
  onRefresh,
  isLoading = false,
  errorMessage,
  currentUrl,
}: CrawlManagerProps) {
  const [pendingUrl, setPendingUrl] = useState("");
  const [activeScope, setActiveScope] = useState(defaultScope);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingItems, setPendingItems] = useState<Record<string, "remove" | "update">>({});
  const [settingsOpen, setSettingsOpen] = useState(queue.length === 0);
  const initialized = useRef(false);

  useEffect(() => {
    setActiveScope(defaultScope);
  }, [defaultScope]);

  useEffect(() => {
    if (queue.length === 0) {
      setSettingsOpen(true);
    }
  }, [queue.length]);

  useEffect(() => {
    if (initialized.current || !onRefresh) {
      return;
    }
    initialized.current = true;
    void onRefresh().catch((error) => {
      const message = error instanceof Error ? error.message : String(error);
      setActionError((current) => current ?? message);
    });
  }, [onRefresh]);

  const markItemPending = useCallback((id: string, state: "remove" | "update" | null) => {
    setPendingItems((current) => {
      if (state === null) {
        const next = { ...current };
        delete next[id];
        return next;
      }
      return { ...current, [id]: state };
    });
  }, []);

  const handleAdd = useCallback(
    async (url: string) => {
      const trimmed = url.trim();
      if (!trimmed) return;
      let normalized: URL;
      try {
        normalized = new URL(trimmed);
      } catch {
        setFormError("Provide a valid URL starting with http or https.");
        return;
      }
      setIsSubmitting(true);
      setFormError(null);
      setActionError(null);
      try {
        await onAddUrl(normalized.toString(), activeScope);
        await onRefresh?.();
        setPendingUrl("");
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setActionError(message);
      } finally {
        setIsSubmitting(false);
      }
    },
    [activeScope, onAddUrl, onRefresh]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const dropped = parseDroppedUrl(event);
      if (!dropped) return;
      void handleAdd(dropped);
    },
    [handleAdd]
  );

  const handleScopeChange = (scope: CrawlScope) => {
    setActiveScope(scope);
    onScopePresetChange?.(scope);
  };

  const handleRemove = useCallback(
    async (id: string) => {
      markItemPending(id, "remove");
      setActionError(null);
      try {
        await onRemove(id);
        await onRefresh?.();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setActionError(message);
      } finally {
        markItemPending(id, null);
      }
    },
    [markItemPending, onRefresh, onRemove]
  );

  const handleScopeUpdate = useCallback(
    async (id: string, scope: CrawlScope) => {
      markItemPending(id, "update");
      setActionError(null);
      try {
        await onUpdateScope(id, scope);
        await onRefresh?.();
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        setActionError(message);
      } finally {
        markItemPending(id, null);
      }
    },
    [markItemPending, onRefresh, onUpdateScope]
  );

  const currentHostname = useMemo(() => safeHostname(currentUrl ?? undefined), [currentUrl]);
  const currentSeed = useMemo(() => {
    if (!currentHostname) {
      return null;
    }
    return queue.find((item) => safeHostname(item.url) === currentHostname) ?? null;
  }, [currentHostname, queue]);
  const fallbackSeed = useMemo(() => (queue.length > 0 ? queue[0] : null), [queue]);
  const summarySeed = currentSeed ?? fallbackSeed;
  const summaryStats = useMemo(() => extractSeedStats(summarySeed?.extras), [summarySeed]);
  const domainLabel = currentHostname ?? (summarySeed ? safeHostname(summarySeed.url) : null);
  const scopeLabel = summarySeed ? SCOPE_LABEL[summarySeed.scope] : null;
  const summaryNotes = summarySeed?.notes?.trim() ? summarySeed.notes.trim() : null;
  const coverageLabel = computeCoverage(
    summaryStats.indexedDocuments,
    summaryStats.availableDocuments
  );
  const indexedValue = formatCount(summaryStats.indexedDocuments);
  const availableValue = formatCount(summaryStats.availableDocuments);
  const lastCrawl = formatTimestampParts(
    summaryStats.lastCrawledAt ?? summaryStats.lastIndexedAt ?? summarySeed?.updatedAt
  );
  const lastVisit = formatTimestampParts(summaryStats.lastVisitedAt);
  const lastUpdated = formatTimestampParts(summarySeed?.updatedAt);
  const lastQueued = formatTimestampParts(summarySeed?.createdAt);
  const summaryContext = useMemo(() => {
    if (currentHostname) {
      if (currentSeed) {
        return "Using saved crawl seed for this domain.";
      }
      return "Domain not yet queued. Add it below to start crawling.";
    }
    if (summarySeed) {
      const fallbackHost = safeHostname(summarySeed.url) ?? summarySeed.url;
      return fallbackHost
        ? `Showing most recent queue entry (${fallbackHost}).`
        : "Showing most recent queue entry.";
    }
    return "Queue is empty. Add a domain to begin crawling.";
  }, [currentHostname, currentSeed, summarySeed]);
  const contextTone = currentHostname && !currentSeed ? "text-amber-600" : "text-muted-foreground";
  const queueCount = formatCount(queue.length);
  const queueCountDetail = queue.length === 1 ? "domain" : "domains";
  const aggregateError = actionError ?? errorMessage;

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="space-y-1 border-b bg-muted/40 pb-3">
        <CardTitle className="text-sm font-semibold">Crawl manager</CardTitle>
        <CardDescription className="text-xs">
          Monitor crawl coverage for the active domain and manage queued seeds.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 py-4">
        <section className="space-y-3">
          <div className="rounded-md border bg-background p-4 shadow-sm">
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Current domain
                  </p>
                  <p className="text-lg font-semibold text-foreground">
                    {domainLabel ?? "No domain selected"}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    {scopeLabel && <Badge variant="outline">{scopeLabel}</Badge>}
                    {summarySeed?.directory && summarySeed.directory !== "workspace" && (
                      <Badge variant="secondary">{summarySeed.directory}</Badge>
                    )}
                    {!summarySeed?.editable && summarySeed && (
                      <Badge variant="secondary">Read only</Badge>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    Queue size
                  </p>
                  <p className="text-lg font-semibold text-foreground">{queueCount}</p>
                  {queue.length > 0 && (
                    <p className="text-[11px] text-muted-foreground">{queueCountDetail}</p>
                  )}
                </div>
              </div>
              {summaryNotes && (
                <p className="text-xs text-muted-foreground">{summaryNotes}</p>
              )}
              {summaryContext && (
                <p className={`text-xs ${contextTone}`}>{summaryContext}</p>
              )}
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <SummaryStat
              label="Indexed documents"
              value={indexedValue}
              detail={
                coverageLabel ??
                (summaryStats.indexedDocuments === null ? "No crawl data yet" : null)
              }
            />
            <SummaryStat
              label="Total available"
              value={availableValue}
              detail={
                summaryStats.availableDocuments === null
                  ? "Source has not reported availability"
                  : "Dataset estimate"
              }
            />
            <SummaryStat
              label="Last crawl"
              value={lastCrawl.primary}
              detail={lastCrawl.secondary}
            />
            <SummaryStat
              label="Last visit"
              value={lastVisit.primary}
              detail={lastVisit.secondary}
            />
            <SummaryStat
              label="Seed updated"
              value={lastUpdated.primary}
              detail={lastUpdated.secondary}
            />
            <SummaryStat
              label="Seed created"
              value={lastQueued.primary}
              detail={lastQueued.secondary}
            />
          </div>
        </section>

        <Separator />

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">Queue settings</h3>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => setSettingsOpen((open) => !open)}
              className="gap-1 text-xs"
            >
              {settingsOpen ? (
                <>
                  Hide settings
                  <ChevronUp className="h-3 w-3" />
                </>
              ) : (
                <>
                  Show settings
                  <ChevronDown className="h-3 w-3" />
                </>
              )}
            </Button>
          </div>

          {aggregateError && (
            <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="h-4 w-4" /> {aggregateError}
            </div>
          )}

          {settingsOpen && (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {(Object.keys(SCOPE_LABEL) as CrawlScope[]).map((scope) => (
                  <Button
                    key={scope}
                    size="sm"
                    variant={scope === activeScope ? "default" : "outline"}
                    onClick={() => handleScopeChange(scope)}
                    className="rounded-full text-xs"
                  >
                    {scope === activeScope && <Check className="mr-1 h-3 w-3" />} {SCOPE_LABEL[scope]}
                  </Button>
                ))}
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void handleAdd(pendingUrl);
                }}
                className="flex gap-2"
              >
                <Input
                  placeholder="https://example.com"
                  value={pendingUrl}
                  onChange={(event) => setPendingUrl(event.target.value)}
                  aria-label="URL to crawl"
                />
                <Button type="submit" variant="secondary" disabled={isSubmitting}>
                  Queue
                </Button>
              </form>
              {formError && (
                <div className="flex items-center gap-2 text-xs text-destructive">
                  <AlertCircle className="h-4 w-4" /> {formError}
                </div>
              )}
              <div
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
                className="rounded-md border border-dashed border-muted-foreground/50 p-4 text-center text-xs text-muted-foreground"
              >
                Drop URLs here to queue them for crawl
              </div>
              <Separator className="my-2" />
              {isLoading && (
                <div className="space-y-2" aria-hidden>
                  <Skeleton className="h-14 w-full" />
                  <Skeleton className="h-14 w-full" />
                </div>
              )}
              <div className="space-y-2">
                {queue.length === 0 && !isLoading && (
                  <p className="text-xs text-muted-foreground">Queue is empty.</p>
                )}
                {queue.map((item, index) => (
                  <Fragment key={item.id}>
                    <div className="rounded border p-3 text-sm">
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <p className="break-all font-medium">{item.url}</p>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant="outline">{SCOPE_LABEL[item.scope]}</Badge>
                            {item.directory && item.directory !== "workspace" && (
                              <Badge variant="secondary">{item.directory}</Badge>
                            )}
                            {!item.editable && <Badge variant="secondary">Read only</Badge>}
                            {item.notes && <span>{item.notes}</span>}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label="Remove from queue"
                          onClick={() => void handleRemove(item.id)}
                          disabled={!item.editable || Boolean(pendingItems[item.id]) || isLoading}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs">
                        {(Object.keys(SCOPE_LABEL) as CrawlScope[]).map((scope) => (
                          <Button
                            key={scope}
                            size="sm"
                            variant={scope === item.scope ? "default" : "outline"}
                            className="text-[11px]"
                            onClick={() => void handleScopeUpdate(item.id, scope)}
                            disabled={
                              !item.editable || pendingItems[item.id] === "update" || isLoading
                            }
                          >
                            {SCOPE_LABEL[scope]}
                          </Button>
                        ))}
                      </div>
                    </div>
                    {index < queue.length - 1 && <Separator />}
                  </Fragment>
                ))}
              </div>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
