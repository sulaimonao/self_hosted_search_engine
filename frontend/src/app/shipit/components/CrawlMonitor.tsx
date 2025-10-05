"use client";

import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

type CrawlStatusResponse = {
  ok: boolean;
  data?: {
    phase: string;
    pct: number;
    urls_processed?: number;
    last_url?: string | null;
  };
};

interface CrawlMonitorProps {
  jobId: string;
}

export default function CrawlMonitor({ jobId }: CrawlMonitorProps): JSX.Element {
  const { data } = useSWR<CrawlStatusResponse>(
    `/api/crawl/status?job_id=${encodeURIComponent(jobId)}`,
    api,
    { refreshInterval: 1_000 }
  );
  const status = data?.data;
  const pct = Math.round(status?.pct ?? 0);
  return (
    <div className="p-3 rounded-2xl border space-y-2">
      <div className="flex justify-between text-sm">
        <span>Phase: {status?.phase ?? "queued"}</span>
        <span>{pct}%</span>
      </div>
      <div className="w-full h-2 bg-gray-100 rounded">
        <div
          className="h-2 rounded bg-blue-500"
          style={{ width: `${pct}%` }}
          aria-label="Crawl progress"
        />
      </div>
      <div className="text-xs mt-1 truncate">
        Last URL: {status?.last_url ?? "n/a"}
      </div>
      <div className="text-xs text-gray-500">
        Processed: {status?.urls_processed ?? 0}
      </div>
    </div>
  );
}
