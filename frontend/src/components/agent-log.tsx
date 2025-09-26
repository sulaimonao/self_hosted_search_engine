"use client";

import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Info,
  Loader2,
} from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import type { ReactNode } from "react";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { AgentLogEntry } from "@/lib/types";

interface AgentLogProps {
  entries: AgentLogEntry[];
  isStreaming?: boolean;
}

const STATUS_ICON: Record<"info" | "success" | "warning" | "error", ReactNode> = {
  info: <Info className="h-3 w-3" />,
  success: <CheckCircle2 className="h-3 w-3" />,
  warning: <AlertTriangle className="h-3 w-3" />,
  error: <AlertCircle className="h-3 w-3" />,
};

export function AgentLog({ entries, isStreaming = false }: AgentLogProps) {
  return (
    <div className="flex h-full flex-col rounded-lg border bg-card">
      <div className="flex items-center justify-between px-4 py-2 border-b">
        <div>
          <h3 className="text-sm font-medium">Agent Log</h3>
          <p className="text-xs text-muted-foreground">
            Live trace of decisions, HTTP calls, and queue updates
          </p>
        </div>
        {isStreaming && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      </div>
      <ScrollArea className="flex-1">
        <ol className="space-y-3 px-4 py-3">
          {entries.length === 0 && (
            <li className="text-xs text-muted-foreground">
              Agent activity will appear here once actions begin.
            </li>
          )}
          {entries.map((entry, index) => {
            const status = (entry.status ?? "info") as keyof typeof STATUS_ICON;
            return (
              <li key={entry.id} className="relative pl-5">
                <span
                  className={cn(
                    "absolute left-0 top-1.5 flex h-3 w-3 items-center justify-center",
                    status === "success" && "text-emerald-500",
                    status === "warning" && "text-amber-500",
                    status === "error" && "text-destructive",
                    status === "info" && "text-muted-foreground"
                  )}
                  aria-hidden
                >
                  {STATUS_ICON[status]}
                </span>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">{entry.label}</p>
                  <span className="text-[11px] text-muted-foreground">
                    {formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}
                  </span>
                </div>
                {entry.detail && (
                  <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">
                    {entry.detail}
                  </p>
                )}
                {index < entries.length - 1 && <Separator className="mt-2" />}
              </li>
            );
          })}
        </ol>
      </ScrollArea>
    </div>
  );
}
