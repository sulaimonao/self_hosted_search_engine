"use client";

import "@/autopilot/executor";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import { AlertTriangle, Check, Clipboard, ClipboardCheck, Loader2, X } from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { BrowserAPI, BrowserDiagnosticsReport } from "@/lib/browser-ipc";
import type { Verb } from "@/autopilot/executor";
import { IncidentBus, type BrowserIncident } from "@/diagnostics/incident-bus";

import { BROWSER_DIAGNOSTICS_SCRIPT } from "@shared/browser-diagnostics-script";

type CheckStatus = "pass" | "warn" | "fail";

type DiagnosticsCheck = {
  key: string;
  label: string;
  detail: string;
  status: CheckStatus;
};

type DirectiveStep = Verb & { [key: string]: unknown };

type Directive = {
  steps?: DirectiveStep[];
  [key: string]: unknown;
};

function isDirective(candidate: unknown): candidate is Directive {
  if (!candidate || typeof candidate !== "object") {
    return false;
  }
  const payload = candidate as { steps?: unknown };
  if ("steps" in payload && payload.steps !== undefined && !Array.isArray(payload.steps)) {
    return false;
  }
  return true;
}

function resolveStatusBadge(status: CheckStatus) {
  switch (status) {
    case "pass":
      return { label: "Pass", variant: "secondary" as const, Icon: Check };
    case "warn":
      return { label: "Warn", variant: "outline" as const, Icon: AlertTriangle };
    default:
      return { label: "Fail", variant: "destructive" as const, Icon: X };
  }
}

interface DiagnosticsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  browserAPI?: BrowserAPI;
  webviewRef: RefObject<ElectronWebviewElement | null>;
  supportsWebview?: boolean;
}

export function DiagnosticsDrawer({
  open,
  onOpenChange,
  browserAPI,
  webviewRef,
  supportsWebview = false,
}: DiagnosticsDrawerProps) {
  const [report, setReport] = useState<BrowserDiagnosticsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState("snapshot");
  const [logEntries, setLogEntries] = useState<string[]>([]);
  const [plannerBusy, setPlannerBusy] = useState(false);
  const [headlessBusy, setHeadlessBusy] = useState(false);
  const [incidentSnapshot, setIncidentSnapshot] = useState<BrowserIncident | null>(null);
  const [lastDirective, setLastDirective] = useState<Directive | null>(null);

  const incidentBusRef = useRef<IncidentBus | null>(null);
  if (!incidentBusRef.current) {
    incidentBusRef.current = new IncidentBus();
  }

  const autoPlanKeyRef = useRef<string | null>(null);

  useEffect(() => {
    incidentBusRef.current?.start();
  }, []);

  const appendLog = useCallback((entry: string) => {
    setLogEntries((prev) => {
      const timestamp = new Date().toLocaleTimeString();
      const next = [...prev, `[${timestamp}] ${entry}`];
      return next.slice(-400);
    });
  }, []);

  useEffect(() => {
    if (!open) {
      return;
    }
    const source = new EventSource("/api/progress/__diagnostics__/stream");
    source.onmessage = (event) => {
      appendLog(`[sse] ${event.data}`);
    };
    source.onerror = () => {
      appendLog("[sse] stream disconnected.");
      source.close();
    };
    return () => {
      source.close();
    };
  }, [appendLog, open]);

  const fetchDirective = useCallback(
    async (
      apply: boolean,
      options?: {
        label?: string;
        suppressBusy?: boolean;
        incident?: BrowserIncident | null;
        logPlan?: boolean;
      },
    ): Promise<Directive | null> => {
      const label = options?.label ?? (apply ? "apply" : "plan");
      const incident = options?.incident ?? incidentBusRef.current?.snapshot();
      if (!incident) {
        appendLog(`[self-heal] ${label}: unable to capture incident snapshot.`);
        return null;
      }
      setIncidentSnapshot(incident);
      if (!options?.suppressBusy) {
        setPlannerBusy(true);
      }
      appendLog(`[self-heal] ${label}: requesting directive (apply=${apply}).`);
      try {
        const response = await fetch(`/api/diagnostics/self_heal?apply=${apply ? "true" : "false"}`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(incident),
        });
        const text = await response.text();
        let payload: unknown = {};
        if (text) {
          try {
            payload = JSON.parse(text);
          } catch (err) {
            payload = { raw: text };
            appendLog(`[self-heal] ${label}: failed to parse planner JSON: ${String(err)}`);
          }
        }
        if (!response.ok) {
          appendLog(`[self-heal] ${label}: planner error (${response.status}).`);
          appendLog(`[self-heal] ${label}: payload -> ${JSON.stringify(payload, null, 2)}`);
          return null;
        }
        if (options?.logPlan !== false) {
          appendLog(`[self-heal] ${label}: response ->\n${JSON.stringify(payload, null, 2)}`);
        }
        let directive: Directive | null = null;
        if (payload && typeof payload === "object" && "directive" in payload) {
          const candidate = (payload as { directive?: unknown }).directive;
          if (isDirective(candidate)) {
            directive = candidate;
          }
        }
        if (!directive) {
          appendLog(`[self-heal] ${label}: planner returned no directive.`);
          return null;
        }
        setLastDirective(directive);
        const headlessCount = (directive.steps ?? []).filter((step) => step && step.headless).length;
        if (headlessCount > 0) {
          appendLog(
            `[self-heal] ${label}: directive includes ${headlessCount} headless step${headlessCount === 1 ? "" : "s"}.`,
          );
        }
        return directive;
      } catch (err) {
        appendLog(`[self-heal] ${label}: request failed: ${String(err)}`);
        return null;
      } finally {
        if (!options?.suppressBusy) {
          setPlannerBusy(false);
        }
      }
    },
    [appendLog],
  );

  const handlePlan = useCallback(async () => {
    await fetchDirective(false, { label: "manual plan" });
  }, [fetchDirective]);

  const handleFixInTab = useCallback(async () => {
    const directive = await fetchDirective(true, { label: "in-tab fix" });
    if (!directive) {
      return;
    }
    const steps = Array.isArray(directive.steps) ? directive.steps : [];
    const inTabSteps = steps.filter((step) => step && !step.headless) as Verb[];
    if (inTabSteps.length === 0) {
      appendLog("[self-heal] in-tab fix: no in-tab steps to execute.");
      return;
    }
    const executor = typeof window !== "undefined" ? window.autopilotExecutor : undefined;
    if (!executor) {
      appendLog("[self-heal] in-tab fix: autopilot executor unavailable in this environment.");
      return;
    }
    try {
      await executor.run({ steps: inTabSteps });
      appendLog(`[self-heal] in-tab fix: executed ${inTabSteps.length} step${inTabSteps.length === 1 ? "" : "s"}.`);
    } catch (err) {
      appendLog(`[self-heal] in-tab fix: execution error: ${String(err)}`);
    }
  }, [appendLog, fetchDirective]);

  const handleFixHeadless = useCallback(async () => {
    let directive = lastDirective;
    if (!directive) {
      appendLog("[self-heal] headless fix: no cached directive; requesting a fresh plan.");
      directive = await fetchDirective(true, { label: "headless fix (fresh plan)" });
    }
    if (!directive) {
      appendLog("[self-heal] headless fix: unable to proceed without a directive.");
      return;
    }
    const headlessSteps = (directive.steps ?? []).filter((step) => step && step.headless);
    if (headlessSteps.length === 0) {
      appendLog("[self-heal] headless fix: directive contains no headless steps.");
      return;
    }
    if (typeof window !== "undefined") {
      const proceed = window.confirm(
        "Headless fix will run server-side scripted steps. Do you want to continue?",
      );
      if (!proceed) {
        appendLog("[self-heal] headless fix: execution cancelled by user.");
        return;
      }
    }
    setHeadlessBusy(true);
    try {
      const response = await fetch("/api/diagnostics/self_heal/execute_headless", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ consent: true, directive }),
      });
      const text = await response.text();
      let payload: unknown = {};
      if (text) {
        try {
          payload = JSON.parse(text);
        } catch (err) {
          payload = { raw: text };
          appendLog(`[self-heal] headless fix: failed to parse response JSON: ${String(err)}`);
        }
      }
      if (!response.ok) {
        appendLog(`[self-heal] headless fix: executor error (${response.status}).`);
        appendLog(`[self-heal] headless fix: payload -> ${JSON.stringify(payload, null, 2)}`);
        return;
      }
      appendLog(`[self-heal] headless fix: result ->\n${JSON.stringify(payload, null, 2)}`);
    } catch (err) {
      appendLog(`[self-heal] headless fix: request failed: ${String(err)}`);
    } finally {
      setHeadlessBusy(false);
    }
  }, [appendLog, fetchDirective, lastDirective]);

  const runChecks = useCallback(async () => {
    setError(null);
    setRunning(true);
    autoPlanKeyRef.current = null;
    try {
      let payload: BrowserDiagnosticsReport | null = null;
      if (browserAPI?.runDiagnostics) {
        const response = await browserAPI.runDiagnostics();
        if (!response?.ok) {
          throw new Error(response?.error || "diagnostics_failed");
        }
        payload = response.data ?? null;
      } else {
        const webview = webviewRef.current;
        if (!webview?.executeJavaScript) {
          throw new Error(supportsWebview ? "webview_unavailable" : "diagnostics_unavailable");
        }
        payload = await webview.executeJavaScript<BrowserDiagnosticsReport>(BROWSER_DIAGNOSTICS_SCRIPT, true);
      }
      setReport(payload ?? null);
      if (!payload) {
        setError("Diagnostics completed but returned no data.");
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      setRunning(false);
    }
  }, [browserAPI, supportsWebview, webviewRef]);

  useEffect(() => {
    if (!report) {
      autoPlanKeyRef.current = null;
      return;
    }
    const key = String(report.timestamp ?? "");
    if (!key || autoPlanKeyRef.current === key) {
      return;
    }
    const incident = incidentBusRef.current?.snapshot();
    if (!incident) {
      return;
    }
    const hasSignals = Boolean(
      incident.symptoms.bannerText ||
        (incident.symptoms.consoleErrors && incident.symptoms.consoleErrors.length > 0) ||
        (incident.symptoms.networkErrors && incident.symptoms.networkErrors.length > 0),
    );
    if (!hasSignals) {
      return;
    }
    autoPlanKeyRef.current = key;
    appendLog("[self-heal] diagnostics run detected issues; requesting automatic plan.");
    void fetchDirective(false, {
      label: "auto-plan (diagnostics)",
      suppressBusy: true,
      incident,
    });
  }, [appendLog, fetchDirective, report]);

  const checks: DiagnosticsCheck[] = useMemo(() => {
    if (!report) {
      return [];
    }
    const uaStatus: CheckStatus = report.userAgent ? "pass" : "fail";
    const uaChStatus: CheckStatus = report.uaCh ? "pass" : report.uaChError ? "warn" : "warn";
    const webdriverStatus: CheckStatus = report.webdriver === false || typeof report.webdriver === "undefined" ? "pass" : "fail";
    const webglStatus: CheckStatus = report.webgl.vendor && report.webgl.renderer ? "pass" : report.webgl.error ? "warn" : "warn";
    const cookieStatus: CheckStatus = report.cookies.count !== null ? "pass" : report.cookies.error ? "warn" : "warn";
    let swStatus: CheckStatus = "warn";
    if (report.serviceWorker.status === "registered") {
      swStatus = "pass";
    } else if (!report.serviceWorker.supported || report.serviceWorker.status === "unsupported") {
      swStatus = "warn";
    } else if (report.serviceWorker.error) {
      swStatus = "fail";
    }

    return [
      {
        key: "ua",
        label: "User agent",
        detail: report.userAgent ? report.userAgent : "Unavailable",
        status: uaStatus,
      },
      {
        key: "ua-ch",
        label: "UA-CH",
        detail: report.uaCh ? JSON.stringify(report.uaCh) : report.uaChError || "Not provided",
        status: uaChStatus,
      },
      {
        key: "webdriver",
        label: "navigator.webdriver",
        detail: `${report.webdriver}`,
        status: webdriverStatus,
      },
      {
        key: "webgl",
        label: "WebGL vendor/renderer",
        detail:
          report.webgl.vendor && report.webgl.renderer
            ? `${report.webgl.vendor} / ${report.webgl.renderer}`
            : report.webgl.error || "Unavailable",
        status: webglStatus,
      },
      {
        key: "cookies",
        label: "Cookie count",
        detail:
          report.cookies.count !== null
            ? `${report.cookies.count} cookie${report.cookies.count === 1 ? "" : "s"}`
            : report.cookies.error || "Unavailable",
        status: cookieStatus,
      },
      {
        key: "service-worker",
        label: "Service worker",
        detail: report.serviceWorker.error
          ? report.serviceWorker.error
          : `${report.serviceWorker.status} (${report.serviceWorker.registrations} registrations)`,
        status: swStatus,
      },
    ];
  }, [report]);

  const handleCopy = useCallback(async () => {
    if (!report) {
      return;
    }
    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
      setError(null);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    }
  }, [report]);

  const planDisabled = plannerBusy || running;
  const headlessDisabled = plannerBusy || headlessBusy;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" size="lg" className="w-full max-w-xl">
        <SheetHeader>
          <SheetTitle>Diagnostics</SheetTitle>
          <SheetDescription>
            Validate the embedded Chromium environment before logging into sensitive sites.
          </SheetDescription>
        </SheetHeader>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4 flex flex-1 flex-col gap-4">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="snapshot">Snapshot</TabsTrigger>
            <TabsTrigger value="self-heal">Self-Heal</TabsTrigger>
          </TabsList>
          <TabsContent value="snapshot" className="flex flex-1 flex-col gap-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={runChecks} disabled={running} size="sm">
                {running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                {running ? "Running checks…" : "Run checks"}
              </Button>
              <Button onClick={handleCopy} variant="outline" size="sm" disabled={!report}>
                {copied ? <ClipboardCheck className="mr-2 h-4 w-4" /> : <Clipboard className="mr-2 h-4 w-4" />}
                {copied ? "Copied" : "Copy report"}
              </Button>
            </div>
            {!browserAPI && !supportsWebview ? (
              <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
                Diagnostics require the desktop app or a compatible Electron webview environment.
              </p>
            ) : null}
            {error ? (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>
            ) : null}
            {report ? (
              <ScrollArea className="flex-1 pr-4">
                <div className="space-y-3">
                  <div className="grid gap-2 text-xs text-muted-foreground">
                    <div>
                      <span className="font-medium text-foreground">Last run:</span> {new Date(report.timestamp).toLocaleString()}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Locale:</span> {report.navigatorLanguage ?? "unknown"}
                    </div>
                    <div>
                      <span className="font-medium text-foreground">Navigator languages:</span> {report.navigatorLanguages.join(", ") || "unknown"}
                    </div>
                  </div>
                  <Separator />
                  {checks.map((check) => {
                    const badge = resolveStatusBadge(check.status);
                    const Icon = badge.Icon;
                    return (
                      <div key={check.key} className="flex items-start justify-between gap-3 rounded-md border p-3">
                        <div>
                          <p className="text-sm font-medium">{check.label}</p>
                          <p className="mt-1 break-words text-xs text-muted-foreground whitespace-pre-wrap">{check.detail}</p>
                        </div>
                        <Badge variant={badge.variant} className="flex items-center gap-1 text-xs">
                          <Icon className="h-3 w-3" />
                          {badge.label}
                        </Badge>
                      </div>
                    );
                  })}
                  <Separator />
                  <div>
                    <p className="mb-2 text-sm font-medium">Raw payload</p>
                    <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
                      {JSON.stringify(report, null, 2)}
                    </pre>
                  </div>
                </div>
              </ScrollArea>
            ) : (
              <div className="flex flex-1 items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
                Run diagnostics to generate a report.
              </div>
            )}
          </TabsContent>
          <TabsContent value="self-heal" className="flex flex-1 flex-col gap-4">
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Capture the current incident snapshot and stream planner updates through the diagnostics log.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={handlePlan} disabled={planDisabled}>
                  {plannerBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Plan
                </Button>
                <Button size="sm" variant="secondary" onClick={handleFixInTab} disabled={planDisabled}>
                  {plannerBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Fix in-tab
                </Button>
                <Button size="sm" variant="destructive" onClick={handleFixHeadless} disabled={headlessDisabled}>
                  {headlessBusy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Fix headless
                </Button>
              </div>
            </div>
            {incidentSnapshot ? (
              <div className="space-y-2 rounded-md border p-3">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">Incident snapshot</h3>
                  <span className="text-xs text-muted-foreground">{new Date(incidentSnapshot.ts).toLocaleTimeString()}</span>
                </div>
                <div className="grid gap-1 text-xs text-muted-foreground">
                  <div>
                    <span className="font-medium text-foreground">URL:</span> {incidentSnapshot.url}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Banner:</span> {incidentSnapshot.symptoms.bannerText || "None"}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Console errors:</span> {incidentSnapshot.symptoms.consoleErrors.length}
                  </div>
                  <div>
                    <span className="font-medium text-foreground">Network errors:</span> {incidentSnapshot.symptoms.networkErrors.length}
                  </div>
                </div>
                {incidentSnapshot.domSnippet ? (
                  <div>
                    <p className="mt-2 text-xs font-medium">DOM snippet</p>
                    <pre className="max-h-32 overflow-auto rounded-md bg-muted p-2 text-[11px]">
                      {incidentSnapshot.domSnippet}
                    </pre>
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                The next plan request will capture banner, console, and network signals from this tab.
              </p>
            )}
            <div className="flex flex-1 flex-col gap-2">
              <h3 className="text-sm font-semibold">Self-Heal log</h3>
              <ScrollArea className="h-48 w-full rounded-md border">
                <pre className="whitespace-pre-wrap break-words p-3 text-xs">
                  {logEntries.length > 0 ? logEntries.join("\n") : "Waiting for planner output…"}
                </pre>
              </ScrollArea>
            </div>
          </TabsContent>
        </Tabs>
        <SheetFooter className="pt-0">
          <p className="text-xs text-muted-foreground">
            Tip: Run the checks after signing into a site to confirm cookies and service workers persist across restarts.
          </p>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

