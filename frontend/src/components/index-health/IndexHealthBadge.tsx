"use client";

import { useEffect, useState } from "react";

import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { IndexHealthPanel } from "@/components/index-health/IndexHealthPanel";

type StatusLevel = "green" | "yellow" | "red" | "unknown";

export function IndexHealthBadge() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<StatusLevel>("unknown");

  useEffect(() => {
    let cancelled = false;
    const fetchStatus = async () => {
      try {
        const response = await fetch("/api/index/health");
        if (!response.ok) {
          throw new Error(`status ${response.status}`);
        }
        const payload = (await response.json()) as { status?: string };
        if (!cancelled) {
          const normalized = (payload.status ?? "unknown") as StatusLevel;
          setStatus(["green", "yellow", "red"].includes(normalized) ? normalized : "unknown");
        }
      } catch {
        if (!cancelled) {
          setStatus("red");
        }
      }
    };
    void fetchStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  const glyph: Record<StatusLevel, string> = {
    green: "🟢",
    yellow: "🟡",
    red: "🔴",
    unknown: "⚪️",
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button type="button" className="text-base" title="Index health">
          {glyph[status]}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Index health</DialogTitle>
        </DialogHeader>
        <IndexHealthPanel onRefreshStatus={setStatus} />
      </DialogContent>
    </Dialog>
  );
}

export default IndexHealthBadge;
