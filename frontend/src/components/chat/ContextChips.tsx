"use client";

import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";

import { api } from "@/lib/api";
import type { ChatContext, DiagnosticsSummary } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";

export type ContextChipsProps = {
  activeUrl?: string | null;
  value: ChatContext;
  onChange: (next: ChatContext) => void;
};

type IndexScope = "page" | "domain" | "site";

type DiagnosticsResponse = DiagnosticsSummary & {
  ok?: boolean;
  stdout?: string;
  stderr?: string;
  incidents?: unknown;
};

const scopeOptions: Array<{ value: IndexScope; label: string; description: string }> = [
  { value: "domain", label: "Domain", description: "Index the current host with moderate depth." },
  { value: "site", label: "Site", description: "Allow the crawler to follow sitemap hints and related links." },
  { value: "page", label: "Single page", description: "Treat the URL as a standalone snapshot." },
];

function withDefaults(context: ChatContext): ChatContext {
  return {
    page: context.page ?? null,
    diagnostics: context.diagnostics ?? null,
    db: context.db ?? { enabled: false },
    tools: context.tools ?? { allowIndexing: false },
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
    if (!resolvedActiveUrl) {
      toast({ title: "No page detected", description: "Open a page in the browser to attach it as context.", variant: "destructive" });
      return;
    }
    setPageLoading(true);
    try {
      const params = new URLSearchParams({ url: resolvedActiveUrl, vision: "1" });
      const response = await fetch(api(`/api/page/extract?${params.toString()}`), { cache: "no-store" });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Page extract failed (${response.status})`);
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
  }, [resolvedActiveUrl, toast, updateContext]);

  const handleDiagnostics = useCallback(async () => {
    setDiagLoading(true);
    try {
      const response = await fetch(api("/api/diagnostics/run"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ smoke: true }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Diagnostics failed (${response.status})`);
      }
      const payload = (await response.json()) as DiagnosticsResponse;
      const summary: DiagnosticsSummary = {
        status: payload.status || (payload.ok ? "ok" : "error"),
        summary: payload.summary || payload.stdout?.split("\n")[0] || "Diagnostics completed",
        traceId: payload.traceId,
        checks: payload.checks ?? null,
      };
      updateContext({ diagnostics: summary });
      toast({ title: "Diagnostics attached", description: summary.summary });
    } catch (error) {
      toast({
        title: "Diagnostics error",
        description: error instanceof Error ? error.message : "Unable to run diagnostics",
        variant: "destructive",
      });
    } finally {
      setDiagLoading(false);
    }
  }, [toast, updateContext]);

  const handleIndexPage = useCallback(async () => {
    if (!resolvedActiveUrl) {
      toast({ title: "No page detected", description: "Open a page before indexing it.", variant: "destructive" });
      return;
    }
    setIndexingPage(true);
    try {
      const response = await fetch(api("/api/index/snapshot"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: resolvedActiveUrl }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Snapshot failed (${response.status})`);
      }
      const payload = await response.json();
      updateContext({ tools: { allowIndexing: true } });
      toast({ title: "Indexing queued", description: payload.message || "Shadow indexer will fetch this page shortly." });
    } catch (error) {
      toast({
        title: "Index request failed",
        description: error instanceof Error ? error.message : "Unable to queue the snapshot",
        variant: "destructive",
      });
    } finally {
      setIndexingPage(false);
    }
  }, [resolvedActiveUrl, toast, updateContext]);

  const handleIndexSite = useCallback(async () => {
    const trimmed = indexUrl.trim();
    if (!trimmed) {
      toast({ title: "URL required", description: "Enter a URL to index before submitting.", variant: "destructive" });
      return;
    }
    setIndexingSite(true);
    try {
      const response = await fetch(api("/api/index/site"), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: trimmed, scope: indexScope }),
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Index site failed (${response.status})`);
      }
      const payload = await response.json();
      updateContext({ tools: { allowIndexing: true } });
      toast({ title: "Crawl queued", description: payload.message || "Focused crawl job submitted." });
      setDialogOpen(false);
    } catch (error) {
      toast({
        title: "Unable to index site",
        description: error instanceof Error ? error.message : "Unexpected error while queuing the crawl",
        variant: "destructive",
      });
    } finally {
      setIndexingSite(false);
    }
  }, [indexUrl, indexScope, toast, updateContext]);

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
        <Button type="button" size="sm" variant={context.page ? "secondary" : "outline"} onClick={() => void handleUseCurrentPage()} disabled={pageLoading}>
          {pageLoading ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : null}
          Use current page
        </Button>
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
