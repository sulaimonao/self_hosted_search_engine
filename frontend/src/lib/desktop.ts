import type { BrowserDiagnosticsReport } from "@/lib/types";

declare global {
  interface Window {
    desktop?: DesktopBridge;
  }
}

export interface DesktopSystemCheckReport extends BrowserDiagnosticsReport {
  skipped?: boolean;
}

export interface DesktopExportDiagnosticsResult {
  ok: boolean;
  report?: DesktopSystemCheckReport | null;
  artifactPath?: string | null;
  path?: string | null;
  error?: string | null;
  skipped?: boolean;
}

export type DesktopSystemCheckChannel =
  | "system-check:open-panel"
  | "system-check:initial-report"
  | "system-check:initial-error"
  | "system-check:report-missing"
  | "system-check:report-error"
  | "system-check:skipped";

export interface DesktopBridge {
  runSystemCheck?: (options?: { timeoutMs?: number }) => Promise<DesktopSystemCheckReport | { skipped: boolean } | null>;
  getLastSystemCheck?: () => Promise<DesktopSystemCheckReport | { skipped: boolean } | null>;
  openSystemCheckReport?: () => Promise<{ ok: boolean; missing?: boolean; error?: string | null; path?: string } | void>;
  exportSystemCheckReport?: (
    options?: { timeoutMs?: number; write?: boolean },
  ) => Promise<DesktopExportDiagnosticsResult | void>;
  shadowCapture?: (payload: {
    url: string;
    html?: string;
    text?: string;
    screenshot_b64?: string;
    headers?: Record<string, string>;
    dom_hash?: string;
    outlinks?: { url: string; same_site?: boolean }[];
    policy_id?: string;
    tab_id?: string;
    session_id?: string;
  }) => Promise<unknown> | void;
  indexSearch?: (query: string) => Promise<unknown> | void;
  onSystemCheckEvent?: (
    channel: DesktopSystemCheckChannel,
    handler: (payload: unknown) => void,
  ) => (() => void) | void;
  onShadowToggle?: (handler: () => void) => (() => void) | void;
}

export const desktop: DesktopBridge | undefined =
  typeof window !== "undefined" ? (window as { desktop?: DesktopBridge }).desktop : undefined;
