"use client";

import { useCallback, useMemo, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { Check, Download, FileWarning, FolderOpen, Pause, Play, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { resolveBrowserAPI, type BrowserDownloadState } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";
import { useStableOnOpenChange } from "@/hooks/useStableOnOpenChange";
import { formatDuration, formatFileSize } from "@/lib/format";

function formatProgress(downloadBytes?: number | null, totalBytes?: number | null): number {
  if (!totalBytes || totalBytes <= 0) {
    return downloadBytes && downloadBytes > 0 ? 100 : 0;
  }
  const ratio = Math.min(1, Math.max(0, (downloadBytes ?? 0) / totalBytes));
  return Math.round(ratio * 100);
}

function describeState(state: string): string {
  switch (state) {
    case "completed":
      return "Completed";
    case "paused":
      return "Paused";
    case "cancelled":
      return "Cancelled";
    case "interrupted":
      return "Interrupted";
    default:
      return "In progress";
  }
}

function summarizeBytes(download: BrowserDownloadState): string {
  const received = formatFileSize(download.bytesReceived ?? 0);
  if (download.bytesTotal && download.bytesTotal > 0) {
    return `${received} / ${formatFileSize(download.bytesTotal)}`;
  }
  return `${received} downloaded`;
}

function getDownloadMetrics(download: BrowserDownloadState): { bps: number | null; etaSeconds: number | null } {
  if (download.state === "paused") {
    return { bps: null, etaSeconds: null };
  }
  const startedAt = download.startedAt ?? null;
  if (!startedAt) {
    return { bps: null, etaSeconds: null };
  }
  const referenceTime =
    download.state === "completed" && download.completedAt
      ? download.completedAt
      : Date.now();
  const elapsedSeconds = Math.max(0, (referenceTime - startedAt) / 1000);
  if (elapsedSeconds <= 0) {
    return { bps: null, etaSeconds: null };
  }
  const bytesReceived = download.bytesReceived ?? 0;
  const bps = bytesReceived / elapsedSeconds;
  let etaSeconds: number | null = null;
  if (bps > 0 && download.bytesTotal && download.bytesTotal > bytesReceived) {
    etaSeconds = (download.bytesTotal - bytesReceived) / bps;
  }
  return { bps, etaSeconds };
}

function formatSpeed(bps: number | null): string {
  if (!bps || bps < 1) {
    return "<1 B/s";
  }
  return `${formatFileSize(bps)} /s`;
}

export function DownloadsTray() {
  const { downloadsOpen, setDownloadsOpen, downloadOrder, downloads, removeDownload } = useBrowserRuntimeStore(
    useShallow((state) => ({
      downloadsOpen: state.downloadsOpen,
      setDownloadsOpen: state.setDownloadsOpen,
      downloadOrder: state.downloadOrder,
      downloads: state.downloads,
      removeDownload: state.removeDownload,
    })),
  );
  const api = useMemo(() => resolveBrowserAPI(), []);
  const stableOpenChange = useStableOnOpenChange(downloadsOpen, setDownloadsOpen);
  const [busyMap, setBusyMap] = useState<Record<string, boolean>>({});

  const setBusy = useCallback((id: string, busy: boolean) => {
    setBusyMap((current) => {
      if (!busy) {
        if (!current[id]) {
          return current;
        }
        const next = { ...current };
        delete next[id];
        return next;
      }
      return { ...current, [id]: true };
    });
  }, []);

  const handlePause = useCallback(
    async (id: string) => {
      if (!api) {
        return;
      }
      setBusy(id, true);
      try {
        const result = await api.pauseDownload(id);
        if (!result?.ok) {
          console.warn("[browser] failed to pause download", result?.error);
        }
      } catch (error) {
        console.warn("[browser] failed to pause download", error);
      } finally {
        setBusy(id, false);
      }
    },
    [api, setBusy],
  );

  const handleResume = useCallback(
    async (id: string) => {
      if (!api) {
        return;
      }
      setBusy(id, true);
      try {
        const result = await api.resumeDownload(id);
        if (!result?.ok) {
          console.warn("[browser] failed to resume download", result?.error);
        }
      } catch (error) {
        console.warn("[browser] failed to resume download", error);
      } finally {
        setBusy(id, false);
      }
    },
    [api, setBusy],
  );

  const handleCancel = useCallback(
    async (id: string) => {
      if (!api) {
        return;
      }
      setBusy(id, true);
      try {
        const result = await api.cancelDownload(id);
        if (!result?.ok) {
          console.warn("[browser] failed to cancel download", result?.error);
        }
      } catch (error) {
        console.warn("[browser] failed to cancel download", error);
      } finally {
        setBusy(id, false);
      }
    },
    [api, setBusy],
  );

  const handleClear = useCallback(
    async (id: string) => {
      if (!api) {
        return;
      }
      setBusy(id, true);
      try {
        const result = await api.clearDownload(id);
        if (result?.ok) {
          removeDownload(id);
        } else if (result && !result.ok) {
          console.warn("[browser] failed to clear download", result.error);
        }
      } catch (error) {
        console.warn("[browser] failed to clear download", error);
      } finally {
        setBusy(id, false);
      }
    },
    [api, removeDownload, setBusy],
  );

  const items = useMemo(
    () =>
      downloadOrder
        .map((id) => downloads[id])
        .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    [downloadOrder, downloads],
  );

  return (
    <Sheet open={downloadsOpen} onOpenChange={stableOpenChange}>
      <SheetContent side="bottom" className="h-72">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 text-sm">
            <Download size={16} /> Downloads
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4 flex h-full flex-col gap-3 overflow-y-auto pb-4" role="list" aria-label="Recent downloads">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No downloads yet.</p>
          ) : (
            items.map((item) => {
              const progress = formatProgress(item.bytesReceived, item.bytesTotal);
              const finished = item.state === "completed";
              const failed = item.state === "cancelled" || item.state === "interrupted";
              const paused = item.state === "paused";
              const active = item.state === "in_progress";
              const busy = Boolean(busyMap[item.id]);
              const metrics = active ? getDownloadMetrics(item) : null;
              const speedText = paused
                ? "Paused"
                : active
                  ? formatSpeed(metrics?.bps ?? null)
                  : null;
              const etaText =
                active && metrics?.etaSeconds != null ? formatDuration(metrics.etaSeconds) : null;
              const summary = summarizeBytes(item);
              const labelId = makeDownloadDomId("download-label", item.id);
              const stateId = makeDownloadDomId("download-state", item.id);
              return (
                <div
                  key={item.id}
                  className="rounded-md border p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                  tabIndex={0}
                  role="listitem"
                  aria-labelledby={labelId}
                  aria-describedby={stateId}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p id={labelId} className="truncate text-sm font-medium">
                        {item.filename ?? item.url}
                      </p>
                      <p id={stateId} className="text-xs text-muted-foreground">
                        {describeState(item.state)}
                      </p>
                    </div>
                    {finished ? (
                      <Check size={16} className="text-state-success" />
                    ) : failed ? (
                      <FileWarning size={16} className="text-state-warning" />
                    ) : null}
                  </div>
                  <div className="mt-2 space-y-2">
                    <Progress value={progress} />
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>{summary}</span>
                      {item.completedAt ? (
                        <span>{new Date(item.completedAt).toLocaleTimeString()}</span>
                      ) : null}
                    </div>
                    {(speedText || etaText) && (
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{speedText ?? "—"}</span>
                        {etaText ? <span>~{etaText} remaining</span> : null}
                      </div>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap justify-end gap-2">
                    {active ? (
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => handlePause(item.id)}>
                        <Pause size={14} className="mr-1" /> Pause
                      </Button>
                    ) : null}
                    {paused ? (
                      <Button size="sm" variant="outline" disabled={busy} onClick={() => handleResume(item.id)}>
                        <Play size={14} className="mr-1" /> Resume
                      </Button>
                    ) : null}
                    {(active || paused) && (
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => handleCancel(item.id)}>
                        <X size={14} className="mr-1" /> Cancel
                      </Button>
                    )}
                    {finished ? (
                      <Button size="sm" variant="ghost" disabled={busy} onClick={() => handleClear(item.id)}>
                        <Trash2 size={14} className="mr-1" /> Clear
                      </Button>
                    ) : null}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!item.path}
                      onClick={() => {
                        if (!api || !item.path) return;
                        api
                          .showDownload(item.id)
                          .catch((error) => console.warn("[browser] failed to reveal download", error));
                      }}
                    >
                      <FolderOpen size={14} className="mr-1" /> Show in folder
                    </Button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function makeDownloadDomId(prefix: string, seed: string): string {
  const normalized = seed.replace(/[^a-zA-Z0-9_-]/g, "");
  return `${prefix}-${normalized || "download"}`;
}
