"use client";

import { useState } from "react";

import { api } from "@/app/shipit/lib/api";
import { useApp } from "@/app/shipit/store/useApp";

import CrawlMonitor from "./CrawlMonitor";

type CrawlResponse = {
  ok: boolean;
  data?: {
    job_id: string;
  };
};

export default function FirstRunWizard(): JSX.Element {
  const { features } = useApp();
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

  const llmStatus = features.llm;
  const llmUnavailable = llmStatus === "unavailable";
  const startDisabled = Boolean(jobId);

  return (
    <div className="space-y-3 rounded-2xl border border-border-subtle bg-app-card p-4 text-sm text-fg shadow-subtle">
      <div className="text-base font-semibold">First-Run Setup</div>
      <div className="text-sm text-fg-muted">
        LLM: {llmUnavailable ? "offline" : llmStatus === "available" ? "reachable" : "checking…"}
      </div>
      {llmUnavailable ? (
        <p className="text-sm text-state-warning">
          Ollama is not running, so chat, planning, and autopilot features are disabled. You can still crawl and search locally.
          Start <code>ollama serve</code> and install models from the Control Center when you are ready to enable LLM features.
        </p>
      ) : (
        <p className="text-sm text-muted-foreground">
          Paste one URL per line. You can revisit the Control Center later to tweak model installs or discovery settings.
        </p>
      )}
      <textarea
        className="w-full rounded-md border border-border-subtle bg-app-input p-2 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        value={seeds}
        onChange={(event) => setSeeds(event.target.value)}
      />
      <button
        className="rounded-2xl border border-border-subtle bg-app-card-subtle px-3 py-2 font-medium text-fg transition hover:bg-app-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50"
        type="button"
        onClick={start}
        disabled={startDisabled}
      >
        Start crawl
      </button>
      {error && <div className="text-sm text-state-danger">{error}</div>}
      {jobId && <CrawlMonitor jobId={jobId} />}
    </div>
  );
}
