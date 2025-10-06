"use client";

import { Clock } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PendingDocument } from "@/lib/types";

interface PendingEmbedsCardProps {
  docs: PendingDocument[];
}

function formatTimestamp(value?: number | null): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "--";
  }
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }
  return date.toLocaleTimeString();
}

export function PendingEmbedsCard({ docs }: PendingEmbedsCardProps) {
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">Pending embeds</CardTitle>
          <span className="text-xs text-muted-foreground">{docs.length}</span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {docs.length === 0 ? (
          <p className="text-xs text-muted-foreground">All documents embedded.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {docs.map((doc) => {
              const label = doc.title && doc.title.trim().length > 0 ? doc.title.trim() : doc.url ?? doc.docId;
              return (
                <li key={doc.docId} className="rounded border px-3 py-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span className="truncate font-medium text-foreground">{label}</span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5" aria-hidden />
                      {formatTimestamp(doc.updatedAt)}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span>Retries {doc.retryCount}</span>
                    {doc.lastError && <span className="text-destructive">{doc.lastError}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
