'use client';

import { useMemo } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { BrowserDiagnosticsReport, SystemCheckItem, SystemCheckResponse } from "@/lib/types";

interface SystemCheckPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  systemCheck: SystemCheckResponse | null;
  browserReport: BrowserDiagnosticsReport | null;
  loading?: boolean;
  error?: string | null;
  // Optional correlation id when the API call itself failed
  errorTraceId?: string | null;
  blocking?: boolean;
  skipMessage?: string | null;
  onRetry?: () => void;
  onContinue?: () => void;
  onOpenReport?: () => void;
  onDownloadReport?: () => void;
}

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const normalized = status.toLowerCase();
  if (normalized === "pass") return "default";
  if (normalized === "warn" || normalized === "warning") return "secondary";
  if (normalized === "fail" || normalized === "error") return "destructive";
  if (normalized === "timeout") return "outline";
  if (normalized === "skip") return "secondary";
  return "outline";
}

function statusLabel(status: string): string {
  const normalized = status.toLowerCase();
  switch (normalized) {
    case "pass":
      return "Pass";
    case "fail":
      return "Fail";
    case "warn":
    case "warning":
      return "Warning";
    case "timeout":
      return "Timeout";
    case "skip":
      return "Skipped";
    default:
      return status.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

function CheckList({ title, items }: { title: string; items: SystemCheckItem[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="flex items-start justify-between gap-3 rounded-md border border-muted px-3 py-2 text-sm">
            <div className="space-y-1">
              <p className="font-medium leading-none">{item.title}</p>
              {item.detail ? <p className="text-xs text-muted-foreground">{item.detail}</p> : null}
            </div>
            <Badge variant={statusVariant(item.status)}>{statusLabel(item.status)}</Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SystemCheckPanel({
  open,
  onOpenChange,
  systemCheck,
  browserReport,
  loading = false,
  error = null,
  errorTraceId = null,
  blocking = false,
  skipMessage = null,
  onRetry,
  onContinue,
  onOpenReport,
  onDownloadReport,
}: SystemCheckPanelProps) {
  const backendChecks = systemCheck?.backend?.checks ?? [];
  const diagnosticsStatus = systemCheck?.diagnostics;
  const llmStatus = systemCheck?.llm;
  const llmPayload = (llmStatus?.payload ?? null) as Record<string, unknown> | null;
  const llmChatModels = Array.isArray(llmPayload?.chat_models)
    ? (llmPayload?.chat_models as string[])
    : [];
  const llmAvailableModels = Array.isArray(llmPayload?.available_models)
    ? (llmPayload?.available_models as string[])
    : [];
  const llmConfigured = (llmPayload?.configured ?? null) as
    | { primary?: string | null; fallback?: string | null }
    | null;
  const llmModelsError =
    typeof llmPayload?.models_error === "string" && llmPayload.models_error.trim()
      ? (llmPayload.models_error as string)
      : null;
  const browserChecks = browserReport?.checks ?? [];

  const sections = useMemo(() => {
    const summary: Array<{ key: string; title: string; status: string; detail?: string | null }> = [];
    if (systemCheck) {
      summary.push({
        key: 'backend',
        title: 'Backend summary',
        status: systemCheck.backend?.status ?? 'unknown',
      });
      summary.push({
        key: 'diagnostics',
        title: 'Diagnostics job',
        status: diagnosticsStatus?.status ?? 'unknown',
        detail: diagnosticsStatus?.detail ?? null,
      });
      summary.push({
        key: 'llm',
        title: 'LLM connectivity',
        status: llmStatus?.status ?? 'unknown',
        detail: llmStatus?.detail ?? null,
      });
    }
    if (browserReport) {
      summary.push({
        key: 'browser',
        title: 'Browser diagnostics',
        status: browserReport.summary.status ?? 'unknown',
        detail: browserReport.summary.criticalFailures ? 'Critical browser diagnostics failure' : undefined,
      });
    }
    return summary;
  }, [browserReport, diagnosticsStatus, llmStatus, systemCheck]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl gap-6">
        <DialogHeader>
          <DialogTitle>System Check</DialogTitle>
          <DialogDescription>Verify backend, LLM, and browser readiness before starting the workspace.</DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 rounded-md border border-muted bg-muted/50 px-3 py-2 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Running diagnostics…
          </div>
        ) : null}

        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <AlertTriangle className="mt-0.5 h-4 w-4" />
            <div>
              <p className="font-semibold">System check error</p>
              <p>{error}</p>
              {errorTraceId ? (
                <p className="text-xs text-muted-foreground">
                  Trace: <span className="font-mono">{errorTraceId}</span>
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        {skipMessage ? (
          <div className="rounded-md border border-muted/40 bg-muted/20 px-3 py-2 text-sm text-muted-foreground">
            {skipMessage}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          {sections.map((entry) => (
            <div key={entry.key} className="rounded-md border border-muted px-3 py-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">{entry.title}</p>
                <Badge variant={statusVariant(entry.status)}>{statusLabel(entry.status)}</Badge>
              </div>
              {entry.detail ? <p className="mt-2 text-xs text-muted-foreground">{entry.detail}</p> : null}
              {entry.key === 'backend' && systemCheck?.traceId ? (
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Trace: <span className="font-mono">{systemCheck.traceId}</span>
                </p>
              ) : null}
            </div>
          ))}
        </div>

        <div className="grid gap-4">
          <CheckList title="Backend checks" items={backendChecks} />
          <CheckList title="Browser checks" items={browserChecks} />
          {llmStatus ? (
            <div className="space-y-1 text-sm">
              <h3 className="text-sm font-semibold">LLM details</h3>
              <p className="text-muted-foreground text-xs">
                Reachable: {llmStatus.reachable ? "yes" : "no"}
                {llmPayload && typeof llmPayload === "object"
                  ? (() => {
                      const host = (llmPayload as { host?: string }).host;
                      return host ? ` • Host: ${host}` : "";
                    })()
                  : ""}
              </p>
              <p className="text-xs text-muted-foreground">
                Chat models: {llmChatModels.length > 0 ? llmChatModels.join(", ") : "none reported"}
              </p>
              {llmConfigured?.primary || llmConfigured?.fallback ? (
                <p className="text-xs text-muted-foreground">
                  Configured: {llmConfigured?.primary ?? "(primary unset)"}
                  {llmConfigured?.fallback ? ` • Fallback: ${llmConfigured.fallback}` : ""}
                </p>
              ) : null}
              {llmAvailableModels.length > 0 ? (
                <p className="text-xs text-muted-foreground">
                  Available models: {llmAvailableModels.join(", ")}
                </p>
              ) : null}
              {llmModelsError ? (
                <p className="text-xs text-destructive">
                  Model inventory error: {llmModelsError}
                </p>
              ) : null}
            </div>
          ) : null}
          {diagnosticsStatus ? (
            <div className="space-y-1 text-sm">
              <h3 className="text-sm font-semibold">Diagnostics job</h3>
              <p className="text-xs text-muted-foreground">Job ID: {diagnosticsStatus.job_id}</p>
              {typeof diagnosticsStatus.duration_ms === 'number' ? (
                <p className="text-xs text-muted-foreground">Duration: {diagnosticsStatus.duration_ms} ms</p>
              ) : null}
            </div>
          ) : null}
          {browserReport ? (
            <div className="space-y-1 text-sm">
              <h3 className="text-sm font-semibold">Browser diagnostics</h3>
              <p className="text-xs text-muted-foreground">Captured at {browserReport.generatedAt}</p>
              <p className="text-xs text-muted-foreground">Timeout: {browserReport.timeoutMs} ms</p>
              {typeof browserReport.durationMs === "number" ? (
                <p className="text-xs text-muted-foreground">Duration: {browserReport.durationMs} ms</p>
              ) : null}
              {Array.isArray(browserReport.logs) ? (
                <p className="text-xs text-muted-foreground">
                  Log entries: {browserReport.logs.length} · Events: {Array.isArray(browserReport.trace) ? browserReport.trace.length : 0}
                </p>
              ) : null}
              {browserReport.metadata ? (
                <p className="text-xs text-muted-foreground">
                  Engine: Electron {browserReport.metadata.electron ?? "?"} · Chromium {browserReport.metadata.chrome ?? "?"} · Platform {browserReport.metadata.platform ?? "?"}/{browserReport.metadata.arch ?? "?"}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {systemCheck?.generated_at ? <span>Backend snapshot: {systemCheck.generated_at}</span> : null}
            {onOpenReport ? (
              <button
                type="button"
                className="font-medium text-primary underline-offset-2 hover:underline"
                onClick={onOpenReport}
              >
                Open browser diagnostics report
              </button>
            ) : null}
            {onDownloadReport ? (
              <button
                type="button"
                className="font-medium text-primary underline-offset-2 hover:underline"
                onClick={onDownloadReport}
              >
                Download full diagnostics
              </button>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={onRetry} disabled={loading || !onRetry}>
              Re-run
            </Button>
            <Button size="sm" onClick={onContinue} disabled={Boolean(blocking) || loading}>
              Continue
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
