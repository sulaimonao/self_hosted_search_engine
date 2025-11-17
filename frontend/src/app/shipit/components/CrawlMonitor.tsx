"use client";

import { useEffect, useState } from "react";

import { api, openProgressStream } from "@/app/shipit/lib/api";

interface CrawlStatusState {
  phase: string;
  pct: number;
  urlsProcessed: number;
  lastUrl: string | null;
}

interface CrawlMonitorProps {
  jobId: string;
}

export default function CrawlMonitor({ jobId }: CrawlMonitorProps): JSX.Element {
  const [status, setStatus] = useState<CrawlStatusState>({
    phase: "queued",
    pct: 0,
    urlsProcessed: 0,
    lastUrl: null,
  });

  useEffect(() => {
    if (!jobId) {
      return;
    }
    let active = true;
    let source: EventSource | null = null;

    const updateState = (payload: Record<string, unknown>) => {
      setStatus((prev) => {
        const phase = typeof payload.phase === "string" ? payload.phase : prev.phase;
        const pctValue =
          typeof payload.pct === "number"
            ? payload.pct
            : typeof payload.progress === "number"
            ? payload.progress * 100
            : undefined;
        const pct = pctValue !== undefined ? Math.max(0, Math.min(100, Math.round(pctValue))) : prev.pct;
        const urlsProcessed =
          typeof payload.urls_processed === "number"
            ? payload.urls_processed
            : typeof payload.urlsProcessed === "number"
            ? payload.urlsProcessed
            : prev.urlsProcessed;
        const lastUrl =
          typeof payload.last_url === "string"
            ? payload.last_url
            : typeof payload.lastUrl === "string"
            ? payload.lastUrl
            : prev.lastUrl;
        return { phase, pct, urlsProcessed, lastUrl: lastUrl ?? null };
      });
    };

    const handleEvent = (eventData: unknown) => {
      if (!eventData || typeof eventData !== "object") {
        return;
      }
      const record = eventData as Record<string, unknown>;
      if (record.status && typeof record.status === "object") {
        updateState(record.status as Record<string, unknown>);
        return;
      }
      updateState(record);
    };

    const startPolling = async () => {
      while (active) {
        try {
          const response = await api<{ ok: boolean; data?: Record<string, unknown> }>(
            `/api/crawl/status?job_id=${encodeURIComponent(jobId)}`,
          );
          if (response.data) {
            updateState(response.data);
          }
          const done = response.data?.phase === "completed" || response.data?.phase === "finished";
          if (done) {
            break;
          }
        } catch {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1_500));
      }
    };

    try {
      source = openProgressStream(jobId);
      source.onmessage = (event) => {
        if (!event.data) return;
        try {
          const parsed = JSON.parse(event.data) as unknown;
          handleEvent(parsed);
        } catch {
          // ignore malformed chunk
        }
      };
      source.onerror = () => {
        source?.close();
        source = null;
        if (active) {
          void startPolling();
        }
      };
    } catch {
      void startPolling();
    }

    return () => {
      active = false;
      source?.close();
    };
  }, [jobId]);

  const pct = Math.round(status.pct);

  return (
    <div className="space-y-2 rounded-xl border border-border-subtle bg-app-card p-3 text-sm text-fg shadow-subtle">
      <div className="flex justify-between">
        <span>Phase: {status.phase}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-2 w-full rounded-full bg-app-subtle">
        <div
          className="h-2 rounded-full bg-accent transition-all"
          style={{ width: `${pct}%` }}
          aria-label="Crawl progress"
        />
      </div>
      <div className="mt-1 truncate text-xs text-fg-muted">
        Last URL: {status.lastUrl ?? "n/a"}
      </div>
      <div className="text-xs text-fg-muted">Processed: {status.urlsProcessed}</div>
    </div>
  );
}
