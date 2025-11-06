"use client";

import React, { useEffect, useState } from "react";

type Entry = { event?: string; level?: string; ts?: string; timestamp?: string; msg?: string; meta?: Record<string, unknown> | null };

export default function LogsPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    const fetchLogs = async () => {
      setLoading(true);
      try {
        const base = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_URL || "http://127.0.0.1:5050";
        const res = await fetch(`${base.replace(/\/$/, '')}/api/logs/recent?n=200`);
        const payload = await res.json();
        if (mounted && payload && payload.entries) {
          setEntries(payload.entries.slice().reverse());
        }
      } catch {
        // ignore
      } finally {
        if (mounted) setLoading(false);
      }
    };
    fetchLogs();
    const id = setInterval(fetchLogs, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="p-4">
      <h2 className="text-xl font-semibold mb-2">Recent Telemetry</h2>
      {loading && <div>Loading…</div>}
      <div className="space-y-2">
        {entries.map((e, i) => (
          <div key={i} className="p-2 border rounded">
            <div className="text-sm text-gray-600">{e.ts ?? e.timestamp}</div>
            <div className="font-mono text-sm">{e.event} — {e.level}</div>
            <div className="mt-1">{e.msg ?? JSON.stringify(e.meta)?.slice(0, 200)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
