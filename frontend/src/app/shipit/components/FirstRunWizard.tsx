"use client";

import { useState } from "react";
import useSWR from "swr";

import { api } from "@/app/shipit/lib/api";

import CrawlMonitor from "./CrawlMonitor";

type HealthResponse = {
  ok: boolean;
  data?: {
    reachable: boolean;
  };
};

type CrawlResponse = {
  ok: boolean;
  data?: {
    job_id: string;
  };
};

export default function FirstRunWizard(): JSX.Element {
  const { data } = useSWR<HealthResponse>("/api/llm/health", api);
  const [seeds, setSeeds] = useState<string>("https://example.com");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start(): Promise<void> {
    setError(null);
    const entries = seeds
      .split(/\s+/)
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
    if (entries.length === 0) {
      setError("Add at least one seed URL");
      return;
    }
    try {
      const response = await api<CrawlResponse>("/api/crawl", {
        method: "POST",
        body: JSON.stringify({ seeds: entries, mode: "fresh" }),
      });
      const id = response.data?.job_id;
      if (id) {
        setJobId(id);
      } else {
        setError("Crawl enqueue failed");
      }
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Request failed");
    }
  }

  const reachable = data?.data?.reachable ?? false;

  return (
    <div className="p-4 border rounded-2xl space-y-3">
      <div className="font-semibold">First-Run Setup</div>
      <div>LLM: {reachable ? "reachable" : "not reachable"}</div>
      <textarea
        className="w-full border rounded p-2"
        value={seeds}
        onChange={(event) => setSeeds(event.target.value)}
      />
      <button className="px-3 py-2 rounded-2xl border" type="button" onClick={start}>
        Start crawl
      </button>
      {error && <div className="text-sm text-red-600">{error}</div>}
      {jobId && <CrawlMonitor jobId={jobId} />}
    </div>
  );
}
