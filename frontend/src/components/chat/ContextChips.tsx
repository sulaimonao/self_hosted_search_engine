"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";

import { api } from "@/lib/api";
import { apiClient } from "@/lib/backend/apiClient";
import type { ChatContext, DiagnosticsSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

export type ContextChipsProps = {
  activeUrl?: string | null;
  value: ChatContext;
  onChange: (next: ChatContext) => void;
};

type IndexScope = "page" | "domain" | "site";

const scopeOptions: Array<{ value: IndexScope; label: string; description: string }> = [
  { value: "domain", label: "Domain", description: "Index the current host with moderate depth." },
  { value: "site", label: "Site", description: "Allow the crawler to follow sitemap hints and related links." },
  { value: "page", label: "Single page", description: "Treat the URL as a standalone snapshot." },
];

const scopeLabels: Record<IndexScope, string> = {
  domain: "Domain",
  site: "Site",
  page: "Single page",
};

type SnapshotJobResponse = {
  jobId?: string | null;
  status?: string | null;
  phase?: string | null;
  url?: string | null;
  message?: string | null;
};

type SiteJobResponse = {
  jobId?: string | null;
  status?: string | null;
  created?: string | null;
  scope?: string | null;
  query?: string | null;
};

function describeTarget(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname || url;
  } catch {
    return url;
  }
}

function withDefaults(context: ChatContext): ChatContext {
  return {
    page: context.page ?? null,
    diagnostics: context.diagnostics ?? null,
    db: context.db ?? { enabled: false },
    tools: context.tools ?? { allowIndexing: false },
    domainSnapshot: context.domainSnapshot ?? null,
    pageSnapshot: context.pageSnapshot ?? null,
  };
}

function summarizeDiagnostics(diag: DiagnosticsSummary | null): string {
  if (!diag) return "No diagnostics attached";
  const status = diag.status || "unknown";
  const summary = diag.summary || "No summary";
  return `${status}: ${summary}`;
}

export function ContextChips({ activeUrl, value, onChange }: ContextChipsProps) {
  const context = useMemo(() => withDefaults(value), [value]);
  const { toast } = useToast();
  const [pageLoading, setPageLoading] = useState(false);
  const [diagLoading, setDiagLoading] = useState(false);
  const [indexingPage, setIndexingPage] = useState(false);
  const [indexingSite, setIndexingSite] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [indexUrl, setIndexUrl] = useState<string>(activeUrl ?? "");
  const [indexScope, setIndexScope] = useState<IndexScope>("domain");
  const [pageInfo, setPageInfo] = useState<{ url: string | null; title: string | null; html: string | null }>({
    url: activeUrl ?? null,
    title: null,
    html: null,
  });

  useEffect(() => {
    if (dialogOpen) return;
    if (activeUrl) {
      setIndexUrl(activeUrl);
    }
  }, [activeUrl, dialogOpen]);

  const resolvedActiveUrl = useMemo(() => {
    const trimmed = (activeUrl || "").trim();
    return trimmed || null;
  }, [activeUrl]);

  useEffect(() => {
    if (typeof window === "undefined") {
      setPageInfo((prev) => ({ ...prev, url: resolvedActiveUrl }));
      return;
    }
    const apiBridge = resolveBrowserAPI();
    if (!apiBridge?.getActiveTabInfo) {
      setPageInfo((prev) => ({ ...prev, url: resolvedActiveUrl }));
      return;
    }
    let cancelled = false;
    void apiBridge
      .getActiveTabInfo()
      .then((info) => {
        if (cancelled) {
          return;
        }
        if (info) {
          setPageInfo({
            url: info.url?.trim() || resolvedActiveUrl,
            title: info.title ?? null,
            html: info.html ?? null,
          });
        } else {
          setPageInfo((prev) => ({ ...prev, url: resolvedActiveUrl ?? prev.url ?? null, html: null }));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPageInfo((prev) => ({ ...prev, url: resolvedActiveUrl ?? prev.url ?? null, html: null }));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [resolvedActiveUrl]);

  const resolvedPageUrl = pageInfo.url ?? resolvedActiveUrl;
  const pageHostname = useMemo(() => {
    if (!resolvedPageUrl) {
      return null;
    }
    try {
      return new URL(resolvedPageUrl).hostname;
    } catch {
      return null;
    }
  }, [resolvedPageUrl]);

  const updateContext = useCallback(
    (patch: Partial<ChatContext>) => {
      const next: ChatContext = withDefaults({
        ...context,
        ...patch,
      });
      if (!next.db?.enabled) {
        next.db = { enabled: false };
      }
      if (!next.tools?.allowIndexing) {
        next.tools = { allowIndexing: false };
      }
      onChange(next);
    },
    [context, onChange],
  );

  const handleUseCurrentPage = useCallback(async () => {
    setPageLoading(true);
    let activeInfo: { url?: string | null; title?: string | null; html?: string | null } | null = null;
    const apiBridge = resolveBrowserAPI();
    if (apiBridge?.getActiveTabInfo) {
      try {
        activeInfo = await apiBridge.getActiveTabInfo();
      } catch (error) {
        console.warn("[context] failed to read active tab info", error);
      }
    }
    const targetUrl = activeInfo?.url?.trim() || resolvedActiveUrl;
    if (!targetUrl) {
      setPageLoading(false);
      toast({
        title: "No URL to index",
        description: "Open a page in the browser to attach it as context.",
        variant: "warning",
      });
      return;
    }
    try {
      const body: Record<string, unknown> = { source_url: targetUrl };
      const htmlPayload = activeInfo?.html ?? pageInfo.html ?? null;
      if (htmlPayload && htmlPayload.trim()) {
        body.html = htmlPayload;
      }
      const titleHint = activeInfo?.title ?? pageInfo.title;
      if (titleHint) {
        body.title = titleHint;
      }
      const query = body.html ? "" : "?vision=1";
      const response = await fetch(api(`/api/extract${query}`), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        let message = `Page extract failed (${response.status})`;
        try {
          const detail = await response.json();
          if (response.status === 400 && detail?.error === "source_url_required") {
            toast({
              title: "No URL to index",
              description: "Open a page in the browser to attach it as context.",
              variant: "warning",
            });
            return;
          }
          if (typeof detail?.message === "string" && detail.message.trim()) {
            message = detail.message.trim();
          } else if (typeof detail?.error === "string" && detail.error.trim()) {
            message = detail.error.trim();
          }
        } catch {
          const text = await response.text();
          message = text || message;
        }
        throw new Error(message);
      }
      const payload = await response.json();
      updateContext({ page: payload });
      toast({ title: "Page attached", description: "The current page will be summarized for the next reply." });
    } catch (error) {
      toast({
        title: "Unable to fetch page",
        description: error instanceof Error ? error.message : "Unexpected error while extracting the page",
        variant: "destructive",
      });
    } finally {
      setPageLoading(false);
    }
  }, [pageInfo.html, pageInfo.title, resolvedActiveUrl, toast, updateContext]);

  const handleDiagnostics = useCallback(async () => {
    setDiagLoading(true);
    try {
      const snapshot = await apiClient.get<Record<string, unknown>>("/api/dev/diag/snapshot");
      if (!snapshot || typeof snapshot !== "object") {
        throw new Error("Unexpected diagnostics payload");
      }
      const status = typeof snapshot.status === "string" && snapshot.status.trim() ? snapshot.status.trim() : "attached";
      const summaryText = typeof snapshot.summary === "string" && snapshot.summary.trim().length > 0 ? snapshot.summary.trim() : "Desktop diagnostics snapshot attached";
      const traceId =
        typeof snapshot.trace_id === "string"
          ? snapshot.trace_id
          : typeof snapshot.traceId === "string"
          ? snapshot.traceId
          : undefined;
      const normalized: DiagnosticsSummary = {
        status,
        summary: summaryText,
        traceId: traceId ?? null,
        checks: [
          {
            id: "desktop_snapshot",
            status: "info",
            detail: JSON.stringify(snapshot),
          },
        ],
        snapshot,
      };
      updateContext({ diagnostics: normalized });
      toast({ title: "Diagnostics attached", description: "Latest desktop diagnostics will be included." });
    } catch (error) {
      toast({
        title: "Diagnostics unavailable",
        description: error instanceof Error ? error.message : "Unable to fetch diagnostics snapshot",
        variant: "destructive",
      });
    } finally {
      setDiagLoading(false);
    }
  }, [toast, updateContext]);

  const handleIndexPage = useCallback(async () => {
    const targetUrl = resolvedPageUrl?.trim();
    if (!targetUrl) {
      toast({
        title: "No URL to index",
        description: "Open a page in the browser to queue it for indexing.",
        variant: "warning",
      });
      return;
    }
    setIndexingPage(true);
    try {
      const payload = await apiClient.post<SnapshotJobResponse>("/api/index/snapshot", { url: targetUrl });
      toast({
        title: "Page queued",
        description: payload.message ?? `Queued snapshot for ${describeTarget(targetUrl)}.`,
      });
    } catch (error) {
      toast({
        title: "Unable to index page",
        description: error instanceof Error ? error.message : "Unexpected error while queuing snapshot",
        variant: "destructive",
      });
    } finally {
      setIndexingPage(false);
    }
  }, [resolvedPageUrl, toast]);

  const handleIndexSite = useCallback(async () => {
    const targetUrl = indexUrl.trim();
    if (!targetUrl) {
      toast({
        title: "URL required",
        description: "Enter a valid URL before queuing a crawl.",
        variant: "warning",
      });
      return;
    }
    setIndexingSite(true);
    try {
      if (indexScope === "page") {
        const payload = await apiClient.post<SnapshotJobResponse>("/api/index/snapshot", { url: targetUrl });
        toast({
          title: "Page queued",
          description: payload.message ?? `Queued snapshot for ${describeTarget(targetUrl)}.`,
        });
      } else {
        const payload = await apiClient.post<SiteJobResponse>("/api/index/site", { url: targetUrl, scope: indexScope });
        const label = scopeLabels[indexScope] ?? indexScope;
        const detail = payload.jobId ? `Job ${payload.jobId}` : "Crawl job";
        toast({
          title: `${label} crawl queued`,
          description: `${detail} scheduled for ${describeTarget(targetUrl)}.`,
        });
      }
      setDialogOpen(false);
    } catch (error) {
      toast({
        title: "Unable to queue index job",
        description: error instanceof Error ? error.message : "Unexpected error while queuing crawl",
        variant: "destructive",
      });
    } finally {
      setIndexingSite(false);
    }
  }, [indexScope, indexUrl, toast]);

  const chips = useMemo(() => {
    const entries: Array<{ key: string; label: string; detail?: string; removable?: boolean; onRemove?: () => void; extra?: ReactNode }> = [];
    if (context.page) {
      entries.push({
        key: "page",
        label: context.page.title || context.page.url || "Current page",
        detail: context.page.url || undefined,
        removable: true,
        onRemove: () => updateContext({ page: null }),
      });
    }
    if (context.diagnostics) {
      entries.push({
        key: "diagnostics",
        label: summarizeDiagnostics(context.diagnostics),
        removable: true,
        onRemove: () => updateContext({ diagnostics: null }),
        extra: (
          <Button type="button" variant="ghost" size="icon" className="h-6 w-6" onClick={() => void handleDiagnostics()}>
            <RefreshCw className="h-3.5 w-3.5" />
            <span className="sr-only">Re-run diagnostics</span>
          </Button>
        ),
      });
    }
    if (context.db?.enabled) {
      entries.push({
        key: "db",
        label: "DB access enabled",
        removable: true,
        onRemove: () => updateContext({ db: { enabled: false } }),
      });
    }
    if (context.tools?.allowIndexing) {
      entries.push({ key: "indexing", label: "Indexing tools allowed" });
    }
    return entries;
  }, [context, handleDiagnostics, updateContext]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <TooltipProvider delayDuration={150}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant={context.page ? "secondary" : "outline"}
                onClick={() => void handleUseCurrentPage()}
                disabled={pageLoading || !resolvedPageUrl}
              >
                {pageLoading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
                Use current page{pageHostname ? ` (${pageHostname})` : ""}
              </Button>
            </TooltipTrigger>
            {!resolvedPageUrl ? (
              <TooltipContent>No active browser tab detected.</TooltipContent>
            ) : null}
          </Tooltip>
        </TooltipProvider>
        <Button type="button" size="sm" variant={context.diagnostics ? "secondary" : "outline"} onClick={() => void handleDiagnostics()} disabled={diagLoading}>
          {diagLoading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
          Attach diagnostics
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => void handleIndexPage()} disabled={indexingPage}>
          {indexingPage ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
          Index this page
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setDialogOpen(true)}>
          Index site…
        </Button>
        <Button
          type="button"
          size="sm"
          variant={context.db?.enabled ? "secondary" : "outline"}
          onClick={() => updateContext({ db: { enabled: !context.db?.enabled } })}
        >
          {context.db?.enabled ? "DB access on" : "DB access"}
        </Button>
      </div>
      {chips.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <Badge key={chip.key} variant="outline" className="flex items-center gap-2 px-2 py-1 text-[11px]">
              <div className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{chip.label}</span>
                {chip.detail ? <span className="truncate text-muted-foreground">{chip.detail}</span> : null}
              </div>
              {chip.extra}
              {chip.removable ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-5 w-5"
                  onClick={chip.onRemove}
                >
                  <X className="h-3 w-3" />
                  <span className="sr-only">Remove {chip.label}</span>
                </Button>
              ) : null}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">No extra context attached. Use the chips above to enrich the next reply.</p>
      )}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Index a site</DialogTitle>
            <DialogDescription>Queue the focused crawler to fetch and embed additional pages.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="index-url">
                URL
              </label>
              <Input id="index-url" value={indexUrl} onChange={(event) => setIndexUrl(event.target.value)} placeholder="https://example.com" />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Scope</label>
              <Select value={indexScope} onValueChange={(next) => setIndexScope(next as IndexScope)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {scopeOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      <div className="flex flex-col">
                        <span>{option.label}</span>
                        <span className="text-xs text-muted-foreground">{option.description}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void handleIndexSite()} disabled={indexingSite}>
              {indexingSite ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
              Queue crawl
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default ContextChips;
