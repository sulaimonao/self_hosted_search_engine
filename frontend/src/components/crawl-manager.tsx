"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Check, Trash2 } from "lucide-react";

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
}

const SCOPE_LABEL: Record<CrawlScope, string> = {
  page: "This page",
  domain: "This domain",
  "allowed-list": "Allowed list",
  custom: "Custom scope",
};

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
}: CrawlManagerProps) {
  const [pendingUrl, setPendingUrl] = useState("");
  const [activeScope, setActiveScope] = useState(defaultScope);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingItems, setPendingItems] = useState<Record<string, "remove" | "update">>({});
  const initialized = useRef(false);

  useEffect(() => {
    setActiveScope(defaultScope);
  }, [defaultScope]);

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

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">Crawl manager</CardTitle>
        <CardDescription className="text-xs">
          Drop URLs from the preview or paste manually. Actions require approval.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {(Object.keys(SCOPE_LABEL) as CrawlScope[]).map((scope) => (
            <Button
              key={scope}
              size="sm"
              variant={scope === activeScope ? "default" : "outline"}
              onClick={() => handleScopeChange(scope)}
              className="rounded-full text-xs"
            >
              {scope === activeScope && <Check className="h-3 w-3 mr-1" />} {SCOPE_LABEL[scope]}
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
        {(actionError || errorMessage) && (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" /> {actionError ?? errorMessage}
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
                    <p className="font-medium break-all">{item.url}</p>
                    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground items-center">
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
                <div className="mt-2 flex gap-2 flex-wrap text-xs">
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
      </CardContent>
    </Card>
  );
}
