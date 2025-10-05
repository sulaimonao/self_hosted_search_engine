"use client";

import { useMemo } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { useProgress } from "@/hooks/useProgress";

interface ProgressPanelProps {
  jobId: string | null;
}

export function ProgressPanel({ jobId }: ProgressPanelProps) {
  const events = useProgress(jobId);

  const summary = useMemo(() => {
    const stats = { ok: 0, err: 0, indexed: 0, normalized: 0 };
    for (const event of events) {
      switch (event.stage) {
        case "fetch_ok":
          stats.ok += 1;
          break;
        case "fetch_err":
          stats.err += 1;
          break;
        case "index":
        case "index_complete":
          stats.indexed += Number(event.added ?? event.docs_indexed ?? 0);
          break;
        case "normalize_complete":
          stats.normalized += Number(event.docs ?? 0);
          break;
        default:
          break;
      }
    }
    return stats;
  }, [events]);

  if (!jobId) {
    return null;
  }

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Crawl progress</CardTitle>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge variant="outline">Job {jobId.slice(0, 8)}</Badge>
          <span>OK {summary.ok}</span>
          <span>Errors {summary.err}</span>
          <span>Indexed {summary.indexed}</span>
          <span>Docs {summary.normalized}</span>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className="h-32 rounded border bg-muted/40 p-2 text-xs">
          <ul className="space-y-1">
            {events.slice(-100).map((event, index) => (
              <li key={`${event.stage}:${index}`} className="flex items-start justify-between gap-2">
                <span className="font-mono text-[11px] uppercase">{event.stage}</span>
                {typeof event.url === "string" ? (
                  <span className="truncate text-muted-foreground">{event.url}</span>
                ) : null}
              </li>
            ))}
            {events.length === 0 ? <li className="text-muted-foreground">Waiting for events…</li> : null}
          </ul>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

export default ProgressPanel;
