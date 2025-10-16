"use client";

import { useMemo } from "react";
import { Check, Download, FileWarning, FolderOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";

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
    case "cancelled":
      return "Cancelled";
    case "interrupted":
      return "Interrupted";
    default:
      return "In progress";
  }
}

export function DownloadsTray() {
  const downloadsOpen = useBrowserRuntimeStore((state) => state.downloadsOpen);
  const setDownloadsOpen = useBrowserRuntimeStore((state) => state.setDownloadsOpen);
  const downloadOrder = useBrowserRuntimeStore((state) => state.downloadOrder);
  const downloads = useBrowserRuntimeStore((state) => state.downloads);
  const api = useMemo(() => resolveBrowserAPI(), []);

  const items = useMemo(
    () =>
      downloadOrder
        .map((id) => downloads[id])
        .filter((item): item is NonNullable<typeof item> => Boolean(item)),
    [downloadOrder, downloads],
  );

  return (
    <Sheet open={downloadsOpen} onOpenChange={setDownloadsOpen}>
      <SheetContent side="bottom" className="h-72">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2 text-sm">
            <Download size={16} /> Downloads
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4 flex h-full flex-col gap-3 overflow-y-auto pb-4">
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No downloads yet.</p>
          ) : (
            items.map((item) => {
              const progress = formatProgress(item.bytesReceived, item.bytesTotal);
              const finished = item.state === "completed";
              const failed = item.state === "cancelled" || item.state === "interrupted";
              return (
                <div key={item.id} className="rounded-md border p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{item.filename ?? item.url}</p>
                      <p className="text-xs text-muted-foreground">{describeState(item.state)}</p>
                    </div>
                    {finished ? (
                      <Check size={16} className="text-green-500" />
                    ) : failed ? (
                      <FileWarning size={16} className="text-amber-500" />
                    ) : null}
                  </div>
                  <div className="mt-2 space-y-2">
                    <Progress value={progress} />
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {item.bytesReceived ?? 0} / {item.bytesTotal ?? 0} bytes
                      </span>
                      {item.completedAt ? (
                        <span>{new Date(item.completedAt).toLocaleTimeString()}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-2 flex justify-end gap-2">
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
