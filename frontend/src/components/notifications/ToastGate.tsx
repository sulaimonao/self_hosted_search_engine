"use client";

import { useEffect, useRef } from "react";

import { useToast } from "@/components/ui/use-toast";
import { useAppStore } from "@/state/useAppStore";

const IMPORTANT_EVENTS = new Set(["error", "crawl.done"]);

export function ToastGate() {
  const notifications = useAppStore((state) => state.notifications);
  const { toast } = useToast();
  const seenRef = useRef(new Set<string>());

  useEffect(() => {
    const entries = Object.values(notifications)
      .filter((item) => IMPORTANT_EVENTS.has(item.kind))
      .sort((a, b) => b.latest - a.latest);

    for (const entry of entries) {
      const key = `${entry.key}:${entry.latest}`;
      if (seenRef.current.has(key)) continue;
      seenRef.current.add(key);
      toast({
        title: entry.kind === "error" ? "Error" : "Crawl complete",
        description: entry.lastMessage ?? `${entry.count} events`,
        variant: entry.kind === "error" ? "destructive" : "default",
      });
    }
  }, [notifications, toast]);

  return null;
}
