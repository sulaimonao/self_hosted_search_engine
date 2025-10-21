"use client";

import { useCallback, useMemo, useState } from "react";
import { AlertTriangle, Check, Clipboard, ClipboardCheck, Loader2, X } from "lucide-react";

import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { BrowserAPI, BrowserDiagnosticsReport } from "@/lib/browser-ipc";
import { BROWSER_DIAGNOSTICS_SCRIPT } from "@shared/browser-diagnostics-script";

interface DiagnosticsDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  browserAPI?: BrowserAPI;
  webviewRef: React.RefObject<ElectronWebviewElement | null>;
  supportsWebview?: boolean;
}

type CheckStatus = "pass" | "warn" | "fail";

type DiagnosticsCheck = {
  key: string;
  label: string;
  detail: string;
  status: CheckStatus;
};

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

  const runChecks = useCallback(async () => {
    setError(null);
    setRunning(true);
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
        detail: report.webgl.vendor && report.webgl.renderer
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

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" size="lg" className="w-full max-w-xl">
        <SheetHeader>
          <SheetTitle>Diagnostics</SheetTitle>
          <SheetDescription>
            Validate the embedded Chromium environment before logging into sensitive sites.
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
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
                        <p className="mt-1 text-xs text-muted-foreground break-words whitespace-pre-wrap">{check.detail}</p>
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
        </div>
        <SheetFooter className="pt-0">
          <p className="text-xs text-muted-foreground">
            Tip: Run the checks after signing into a site to confirm cookies and service workers persist across restarts.
          </p>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
