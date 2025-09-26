<<<<<<< ours
<<<<<<< ours
export function AgentLog() {
  return (
    <div className="p-4 border-t">
      <p>Agent Log</p>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { JobEvent } from "@/lib/api";
import { toRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface AgentLogProps {
  events: JobEvent[];
  className?: string;
}

const importanceOrder = ["error", "warn", "info", "debug"];

function eventImportance(type: string) {
  const lower = type.toLowerCase();
  const index = importanceOrder.findIndex((item) => lower.includes(item));
  return index === -1 ? importanceOrder.length : index;
}

export function AgentLog({ events, className }: AgentLogProps) {
  const sorted = useMemo(() => [...events].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()), [events]);

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase text-muted-foreground">Agent Log</h3>
        <span className="text-xs text-muted-foreground">{events.length} entries</span>
      </div>
      <Separator className="my-2" />
      <ScrollArea className="flex-1">
        <ol className="space-y-3 pr-2">
          {sorted.map((event) => (
            <li key={`${event.id}-${event.ts}`} className="rounded-lg border border-border bg-card/70 p-3 shadow-sm">
              <div className="flex items-center justify-between gap-2">
                <Badge variant={eventImportance(event.type) <= 1 ? "warning" : "secondary"}>{event.type}</Badge>
                <span className="text-xs text-muted-foreground">{toRelativeTime(new Date(event.ts))}</span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-foreground">{event.message}</p>
              {event.meta && (
                <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
                  {JSON.stringify(event.meta, null, 2)}
                </pre>
              )}
            </li>
          ))}
          {events.length === 0 && <p className="text-sm text-muted-foreground">No activity yet.</p>}
        </ol>
      </ScrollArea>
    </div>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
