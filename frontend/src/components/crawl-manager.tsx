<<<<<<< ours
<<<<<<< ours
export function CrawlManager() {
  return (
    <div className="p-4 border-t">
      <h3 className="font-semibold">Crawl Queue</h3>
      <ul>
        <li>https://example.com</li>
      </ul>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AgentAction, CrawlScope } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface PendingCrawl {
  id: string;
  url: string;
  scope: CrawlScope;
  note?: string;
}

interface CrawlManagerProps {
  items: PendingCrawl[];
  onDropUrl: (url: string) => void;
  onScopeChange: (id: string, scope: CrawlScope) => void;
  onLaunch: (item: PendingCrawl) => void;
  onRemove: (id: string) => void;
  suggestedActions?: AgentAction[];
}

const scopePresets: { label: string; scope: Partial<CrawlScope> }[] = [
  { label: "This page", scope: { maxPages: 1, maxDepth: 0 } },
  { label: "This domain", scope: { maxPages: 25, maxDepth: 2 } },
  { label: "Allowed list", scope: { maxPages: 50, maxDepth: 3 } },
];

export function CrawlManager({ items, onDropUrl, onScopeChange, onLaunch, onRemove, suggestedActions = [] }: CrawlManagerProps) {
  const totalBudget = useMemo(() => items.reduce((sum, item) => sum + item.scope.maxPages, 0), [items]);

  return (
    <Card
      className="relative flex h-full flex-col border-dashed border-primary/30 bg-primary/5"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const url = event.dataTransfer.getData("text/uri-list") || event.dataTransfer.getData("text/plain");
        if (url) {
          onDropUrl(url.trim());
        }
      }}
    >
      <CardHeader className="space-y-2">
        <CardTitle className="text-sm font-semibold uppercase tracking-wide text-primary">To Crawl Queue</CardTitle>
        <p className="text-xs text-muted-foreground">Drag URLs here from the web preview or chat.</p>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary">Budget: {totalBudget} pages</Badge>
          <Badge variant="secondary">Items: {items.length}</Badge>
        </div>
        {suggestedActions.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {suggestedActions.length} agent suggestion{suggestedActions.length > 1 ? "s" : ""} pending approval.
          </p>
        )}
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <ScrollArea className="flex-1 rounded-md border border-dashed border-border/60 bg-background/80 p-2">
          <div className="space-y-3">
            {items.map((item) => (
              <div key={item.id} className="space-y-2 rounded-lg border border-border bg-card p-3 shadow-sm">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-foreground">{item.url}</p>
                  <Button variant="ghost" size="sm" onClick={() => onRemove(item.id)}>
                    Remove
                  </Button>
                </div>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <label className="flex flex-col gap-1">
                    <span className="text-muted-foreground">Max pages</span>
                    <Input
                      type="number"
                      min={1}
                      value={item.scope.maxPages}
                      onChange={(event) =>
                        onScopeChange(item.id, {
                          ...item.scope,
                          maxPages: Number(event.target.value) || item.scope.maxPages,
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-muted-foreground">Depth</span>
                    <Input
                      type="number"
                      min={0}
                      value={item.scope.maxDepth}
                      onChange={(event) =>
                        onScopeChange(item.id, {
                          ...item.scope,
                          maxDepth: Number(event.target.value) || item.scope.maxDepth,
                        })
                      }
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span className="text-muted-foreground">Domains</span>
                    <Input
                      value={item.scope.domains.join(", ")}
                      onChange={(event) =>
                        onScopeChange(item.id, {
                          ...item.scope,
                          domains: event.target.value
                            .split(/[,\s]+/)
                            .map((domain) => domain.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                  </label>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  {scopePresets.map((preset) => (
                    <Button
                      key={preset.label}
                      variant="secondary"
                      size="sm"
                      className={cn("rounded-full px-3", preset.scope.maxPages === item.scope.maxPages && "bg-primary/80 text-white")}
                      onClick={() =>
                        onScopeChange(item.id, {
                          ...item.scope,
                          ...preset.scope,
                        })
                      }
                    >
                      {preset.label}
                    </Button>
                  ))}
                  <Button variant="default" size="sm" onClick={() => onLaunch(item)}>
                    Queue crawl
                  </Button>
                </div>
              </div>
            ))}
            {items.length === 0 && (
              <div className="flex h-40 flex-col items-center justify-center rounded-lg border border-dashed border-border text-sm text-muted-foreground">
                Drop URLs here to stage a crawl plan.
              </div>
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
