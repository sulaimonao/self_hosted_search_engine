"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { triggerDiagnostics } from "@/app/shipit/lib/api";
import type { DiagnosticsResponse } from "@/app/shipit/lib/api";
import { Button } from "@/components/ui/button";

interface ArtifactLink {
  label: string;
  href: string;
}

function extractJobId(payload: Record<string, unknown> | undefined): string | null {
  if (!payload) return null;
  const direct = payload["job_id"] ?? payload["jobId"];
  if (typeof direct === "string" && direct.trim()) {
    return direct.trim();
  }
  const result = payload["result"];
  if (result && typeof result === "object") {
    const nested =
      (result as Record<string, unknown>)["job_id"] ?? (result as Record<string, unknown>)["jobId"];
    if (typeof nested === "string" && nested.trim()) {
      return nested.trim();
    }
  }
  return null;
}

function coerceArtifactLinks(payload: Record<string, unknown> | undefined): ArtifactLink[] {
  if (!payload) return [];
  const links: ArtifactLink[] = [];

  const appendRecord = (record: Record<string, unknown>, prefix: string = "artifact") => {
    const download = record["download_url"] ?? record["url"] ?? record["href"];
    if (typeof download === "string" && download.trim()) {
      const label = typeof record["path"] === "string" && record["path"].trim()
        ? (record["path"] as string).trim()
        : typeof record["label"] === "string" && record["label"].trim()
        ? (record["label"] as string).trim()
        : prefix;
      links.push({ label, href: download.trim() });
    } else if (typeof record["local_path"] === "string" && record["local_path"].trim()) {
      const path = (record["local_path"] as string).trim();
      links.push({ label: path, href: path });
    }
  };

  const scanArray = (value: unknown, prefix: string) => {
    if (!Array.isArray(value)) return;
    value.forEach((entry, index) => {
      if (entry && typeof entry === "object") {
        appendRecord(entry as Record<string, unknown>, `${prefix}-${index + 1}`);
      }
    });
  };

  scanArray(payload["artifacts"], "artifact");
  const result = payload["result"];
  if (result && typeof result === "object") {
    const record = result as Record<string, unknown>;
    scanArray(record["artifacts"], "result-artifact");
    const summaryPath = record["summary_path"] ?? record["summaryPath"];
    if (typeof summaryPath === "string" && summaryPath.trim()) {
      links.push({ label: "Summary", href: summaryPath.trim() });
    }
    const logPaths = record["log_paths"] ?? record["logPaths"];
    if (Array.isArray(logPaths)) {
      logPaths.forEach((entry, index) => {
        if (typeof entry === "string" && entry.trim()) {
          links.push({ label: `Log ${index + 1}`, href: entry.trim() });
        }
      });
    }
  }

  return links;
}

export default function DiagnosticsPage(): JSX.Element {
  const [response, setResponse] = useState<DiagnosticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDiagnostics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await triggerDiagnostics();
      setResponse(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? "Diagnostics failed");
      setError(message);
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void runDiagnostics();
  }, [runDiagnostics]);

  const payload = response?.data;
  const jobId = useMemo(() => extractJobId(payload), [payload]);
  const artifacts = useMemo(() => coerceArtifactLinks(payload), [payload]);
  const pretty = useMemo(() => {
    if (!payload) return null;
    try {
      return JSON.stringify(payload, null, 2);
    } catch {
      return null;
    }
  }, [payload]);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 p-8">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Diagnostics snapshot</h1>
        <p className="text-sm text-muted-foreground">
          Capture repository status, recent logs, and optional pytest discovery directly from the desktop app.
        </p>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Button type="button" onClick={runDiagnostics} disabled={loading}>
            {loading ? "Running…" : "Run diagnostics"}
          </Button>
          {jobId ? (
            <Link
              href={`/api/jobs/${encodeURIComponent(jobId)}/status`}
              target="_blank"
              rel="noreferrer"
              className="text-sm underline"
            >
              View job {jobId}
            </Link>
          ) : null}
        </div>
        <Link
          href="/shipit/diagnostics/self-heal"
          className="text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          Open Self-Heal planner
        </Link>
      </div>

      {error ? <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div> : null}

      {artifacts.length > 0 ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Artifacts</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {artifacts.map((artifact) => (
              <li key={`${artifact.label}-${artifact.href}`}>
                <Link href={artifact.href} target="_blank" rel="noreferrer" className="underline">
                  {artifact.label}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {pretty ? (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Response payload</h2>
          <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted/30 p-4 text-xs leading-relaxed">
            {pretty}
          </pre>
        </section>
      ) : null}

      {!loading && !error && !payload ? (
        <div className="rounded-md border border-muted-foreground/20 bg-muted/10 p-4 text-sm text-muted-foreground">
          Diagnostics response empty. Retry to capture a new snapshot.
        </div>
      ) : null}
    </main>
  );
}
