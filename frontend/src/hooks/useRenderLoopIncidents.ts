"use client";

import { useEffect, useState } from "react";

import { incidentBus, type BrowserIncident } from "@/diagnostics/incident-bus";

export function useRenderLoopIncidents(limit = 10) {
  const [incidents, setIncidents] = useState<BrowserIncident[]>([]);

  useEffect(() => {
    incidentBus.start();
    const unsubscribe = incidentBus.subscribe((entries) => {
      const filtered = entries
        .filter((entry) => entry.kind === "RENDER_LOOP" || entry.message?.includes("[render-loop]"))
        .sort((a, b) => b.ts - a.ts)
        .slice(0, limit);
      setIncidents(filtered);
    });
    return unsubscribe;
  }, [limit]);

  return incidents;
}
