"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/state/useAppStore";

export type ShadowJobSummary = {
  id: string;
  site: string;
  progress: number;
  pending: number;
  eta?: string;
};

export function ShadowPanel() {
  const { shadowEnabled, setShadow } = useAppStore((state) => ({
    shadowEnabled: state.shadowEnabled,
    setShadow: state.setShadow,
  }));
  const [jobs, setJobs] = useState<ShadowJobSummary[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const response = await fetch("/api/shadow/status");
        if (!response.ok) throw new Error("status");
        const payload = await response.json();
        if (!cancelled && Array.isArray(payload?.jobs)) {
          setJobs(payload.jobs);
        }
      } catch {
        if (!cancelled) {
          setJobs([]);
        }
      }
    }

    poll();
    const interval = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="flex h-full w-[26rem] flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">Shadow mode</h3>
        <div className="flex items-center gap-2 text-sm">
          <span>Enabled</span>
          <Switch checked={shadowEnabled} onCheckedChange={setShadow} />
        </div>
      </div>
      <div className="space-y-3 text-xs">
        {jobs.length === 0 ? (
          <p className="text-muted-foreground">No active jobs</p>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="space-y-2 rounded border p-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{job.site}</span>
                <span>{Math.round(job.progress)}%</span>
              </div>
              <Progress value={Math.max(0, Math.min(100, job.progress))} />
              <div className="flex items-center justify-between text-muted-foreground">
                <span>{job.pending} pending</span>
                <span>ETA {job.eta ?? "—"}</span>
              </div>
              <div className="flex items-center justify-end gap-2">
                <Button size="sm" variant="outline">
                  Pause
                </Button>
                <Button size="sm" variant="secondary">
                  Stop
                </Button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
