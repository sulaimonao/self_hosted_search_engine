"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import type { CrawlQueueItem, CrawlScope } from "@/lib/types";

interface CrawlManagerProps {
  queue: CrawlQueueItem[];
  defaultScope: CrawlScope;
  onAddUrl: (url: string, scope: CrawlScope) => void;
  onRemove: (id: string) => void;
  onUpdateScope: (id: string, scope: CrawlScope) => void;
  onScopePresetChange?: (scope: CrawlScope) => void;
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
}: CrawlManagerProps) {
  const [pendingUrl, setPendingUrl] = useState("");
  const [activeScope, setActiveScope] = useState(defaultScope);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setActiveScope(defaultScope);
  }, [defaultScope]);

  const handleAdd = useCallback(
    (url: string) => {
      if (!url.trim()) return;
      try {
        const normalized = new URL(url.trim());
        onAddUrl(normalized.toString(), activeScope);
        setPendingUrl("");
        setError(null);
      } catch {
        setError("Provide a valid URL starting with http or https.");
      }
    },
    [activeScope, onAddUrl]
  );

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const dropped = parseDroppedUrl(event);
      if (!dropped) return;
      handleAdd(dropped);
    },
    [handleAdd]
  );

  const handleScopeChange = (scope: CrawlScope) => {
    setActiveScope(scope);
    onScopePresetChange?.(scope);
  };

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
            handleAdd(pendingUrl);
          }}
          className="flex gap-2"
        >
          <Input
            placeholder="https://example.com"
            value={pendingUrl}
            onChange={(event) => setPendingUrl(event.target.value)}
            aria-label="URL to crawl"
          />
          <Button type="submit" variant="secondary">
            Queue
          </Button>
        </form>
        {error && (
          <div className="flex items-center gap-2 text-xs text-destructive">
            <AlertCircle className="h-4 w-4" /> {error}
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
        <div className="space-y-2">
          {queue.length === 0 && (
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
                      {item.notes && <span>{item.notes}</span>}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Remove from queue"
                    onClick={() => onRemove(item.id)}
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
                      onClick={() => onUpdateScope(item.id, scope)}
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
