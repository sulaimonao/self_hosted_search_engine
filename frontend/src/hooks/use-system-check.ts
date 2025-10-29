'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

import { runSystemCheck } from '@/lib/api';
import type { BrowserDiagnosticsReport, SystemCheckResponse } from '@/lib/types';
import { desktop, type DesktopSystemCheckChannel } from '@/lib/desktop';

interface RunOptions {
  forceBrowser?: boolean;
}

function isBrowserDiagnosticsReport(value: unknown): value is BrowserDiagnosticsReport {
  return Boolean(
    value &&
      typeof value === 'object' &&
      Array.isArray((value as { checks?: unknown }).checks) &&
      typeof (value as { summary?: unknown }).summary === 'object',
  );
}

export interface UseSystemCheckOptions {
  autoRun?: boolean;
  openInitially?: boolean;
}

export interface SystemCheckController {
  open: boolean;
  setOpen: (value: boolean) => void;
  loading: boolean;
  error: string | null;
  backendReport: SystemCheckResponse | null;
  browserReport: BrowserDiagnosticsReport | null;
  skipMessage: string | null;
  blocking: boolean;
  run: (options?: RunOptions) => Promise<void>;
  rerun: () => Promise<void>;
  openReport: () => Promise<void>;
  downloadReport: () => Promise<void>;
}

export function useSystemCheck(options: UseSystemCheckOptions = {}): SystemCheckController {
  const [open, setOpen] = useState(Boolean(options.openInitially));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendReport, setBackendReport] = useState<SystemCheckResponse | null>(null);
  const [browserReport, setBrowserReport] = useState<BrowserDiagnosticsReport | null>(null);
  const [skipMessage, setSkipMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!desktop) {
      setSkipMessage('Browser diagnostics run in the desktop app.');
    }
  }, []);

  const fetchBrowserReport = useCallback(async (force: boolean) => {
    if (!desktop) {
      return null;
    }
    if (force && typeof desktop.runSystemCheck === 'function') {
      const result = await desktop.runSystemCheck({});
      if (result && typeof result === 'object' && 'skipped' in result && (result as { skipped?: boolean }).skipped) {
        setSkipMessage('Browser diagnostics skipped by configuration.');
        return null;
      }
      if (isBrowserDiagnosticsReport(result)) {
        return result;
      }
      return null;
    }
    if (typeof desktop.getLastSystemCheck === 'function') {
      try {
        const result = await desktop.getLastSystemCheck();
        if (result && typeof result === 'object' && 'skipped' in result && (result as { skipped?: boolean }).skipped) {
          setSkipMessage('Browser diagnostics skipped by configuration.');
          return null;
        }
        if (isBrowserDiagnosticsReport(result)) {
          return result;
        }
      } catch {
        return null;
      }
    }
    return null;
  }, []);

  const run = useCallback(
    async (runOptions: RunOptions = {}) => {
      setLoading(true);
      setError(null);
      if (desktop) {
        setSkipMessage(null);
      }
      try {
        const [backend, browser] = await Promise.all([
          runSystemCheck(),
          fetchBrowserReport(Boolean(runOptions.forceBrowser)),
        ]);
        setBackendReport(backend);
        if (browser) {
          setBrowserReport(browser);
        } else if (runOptions.forceBrowser) {
          setBrowserReport(null);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err ?? 'System check failed');
        setError(message);
        throw err;
      } finally {
        setLoading(false);
      }
    },
    [fetchBrowserReport],
  );

  const rerun = useCallback(() => run({ forceBrowser: true }), [run]);

  const downloadReportToFile = useCallback((report: BrowserDiagnosticsReport) => {
    if (typeof window === 'undefined') {
      return;
    }
    const timestamp = typeof report.generatedAt === 'string' ? report.generatedAt : new Date().toISOString();
    const safeStamp = timestamp.replace(/[:\s]/g, '-').replace(/[^0-9A-Za-z._-]/g, '-');
    const fileName = `browser-diagnostics-${safeStamp}.json`;
    const payload = JSON.stringify(report, null, 2);
    const blob = new Blob([payload], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, []);

  useEffect(() => {
    const bridge = desktop;
    if (!bridge?.onSystemCheckEvent) {
      return;
    }
    const unsubscribes: Array<() => void> = [];

    const add = (channel: DesktopSystemCheckChannel, handler: (payload: unknown) => void) => {
      const unsubscribe = bridge.onSystemCheckEvent?.(channel, handler);
      if (typeof unsubscribe === 'function') {
        unsubscribes.push(unsubscribe);
      }
    };

    add('system-check:open-panel', () => {
      setOpen(true);
      void rerun();
    });

    add('system-check:initial-report', (payload) => {
      if (isBrowserDiagnosticsReport(payload)) {
        setBrowserReport(payload);
      }
    });

    add('system-check:initial-error', (payload) => {
      if (payload) {
        setError(typeof payload === 'string' ? payload : 'System check failed');
      }
    });

    add('system-check:report-missing', () => {
      setError('No system check report found yet. Re-run the check to generate one.');
    });

    add('system-check:report-error', (payload) => {
      if (payload) {
        setError(typeof payload === 'string' ? payload : 'Unable to open system check report.');
      }
    });

    add('system-check:skipped', () => {
      setSkipMessage('System check skipped by configuration.');
    });

    return () => {
      unsubscribes.forEach((unsubscribe) => {
        try {
          unsubscribe();
        } catch {
          // ignore
        }
      });
    };
  }, [rerun]);

  useEffect(() => {
    if (desktop?.getLastSystemCheck) {
      desktop
        .getLastSystemCheck()
        .then((report) => {
          if (isBrowserDiagnosticsReport(report)) {
            setBrowserReport(report);
          }
        })
        .catch(() => undefined);
    }
  }, []);

  useEffect(() => {
    if (options.autoRun) {
      setOpen(true);
      void run();
    }
  }, [options.autoRun, run]);

  const openReport = useCallback(async () => {
    if (!desktop?.openSystemCheckReport) {
      setError('System check report is only available in the desktop app.');
      return;
    }
    try {
      const result = await desktop.openSystemCheckReport();
      if (result && typeof result === 'object') {
        const payload = result as { ok?: boolean; missing?: boolean; error?: string | null };
        if (payload.missing) {
          setError('No system check report found. Run the browser diagnostics first.');
        } else if (payload.error) {
          setError(payload.error);
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? 'Failed to open system check report');
      setError(message);
    }
  }, []);

  const downloadReport = useCallback(async () => {
    if (!desktop?.exportSystemCheckReport) {
      if (browserReport) {
        downloadReportToFile(browserReport);
        return;
      }
      setError('System check report is only available in the desktop app.');
      return;
    }
    setLoading(true);
    setError(null);
    setSkipMessage(null);
    try {
      const payload = await desktop.exportSystemCheckReport({ timeoutMs: undefined });
      if (!payload) {
        setError('No diagnostics export result from the desktop app.');
        return;
      }
      if (payload.skipped) {
        setSkipMessage('Browser diagnostics skipped by configuration.');
        return;
      }
      if (!payload.ok) {
        setError(payload.error ?? 'Failed to export browser diagnostics.');
        return;
      }
      const exportedReport = payload.report;
      if (exportedReport) {
        setBrowserReport(exportedReport);
        downloadReportToFile(exportedReport);
      } else if (browserReport) {
        downloadReportToFile(browserReport);
      } else {
        setError('Diagnostics export did not include a report. Re-run the system check and try again.');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err ?? 'Failed to export diagnostics');
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [browserReport, downloadReportToFile]);

  const blocking = useMemo(() => {
    if (skipMessage) {
      return false;
    }
    const backendCritical = backendReport?.summary?.critical_failures === true;
    const browserCritical = browserReport?.summary?.criticalFailures === true;
    return backendCritical || browserCritical;
  }, [backendReport, browserReport, skipMessage]);

  return {
    open,
    setOpen,
    loading,
    error,
    backendReport,
    browserReport,
    skipMessage,
    blocking,
    run,
    rerun,
    openReport,
    downloadReport,
  };
}
