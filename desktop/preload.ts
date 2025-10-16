import { contextBridge, ipcRenderer } from 'electron';

type DesktopSystemCheckChannel =
  | 'system-check:open-panel'
  | 'system-check:initial-report'
  | 'system-check:initial-error'
  | 'system-check:report-missing'
  | 'system-check:report-error'
  | 'system-check:skipped';

type DesktopSystemCheckOptions = {
  timeoutMs?: number;
  write?: boolean;
};

type DesktopSystemCheckReport = Record<string, unknown> & {
  artifactPath?: string | null;
};

type DesktopOpenReportResult = {
  ok: boolean;
  missing?: boolean;
  error?: string | null;
  path?: string | null;
};

type DesktopExportDiagnosticsResult = {
  ok: boolean;
  report?: DesktopSystemCheckReport | null;
  artifactPath?: string | null;
  path?: string | null;
  error?: string | null;
  skipped?: boolean;
};

type ShadowSnapshot = {
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
};

type SystemCheckHandler = (payload: unknown) => void;

type ShadowToggleHandler = () => void;

type Unsubscribe = () => void;

type DesktopBridge = {
  runSystemCheck: (options?: DesktopSystemCheckOptions) => Promise<DesktopSystemCheckReport | { skipped: true } | null>;
  getLastSystemCheck: () => Promise<DesktopSystemCheckReport | { skipped: true } | null>;
  openSystemCheckReport: () => Promise<DesktopOpenReportResult>;
  exportSystemCheckReport: (options?: DesktopSystemCheckOptions) => Promise<DesktopExportDiagnosticsResult>;
  onSystemCheckEvent: (channel: DesktopSystemCheckChannel, handler: SystemCheckHandler) => Unsubscribe;
  shadowCapture: (payload: ShadowSnapshot) => Promise<unknown>;
  indexSearch: (query: string) => Promise<unknown>;
  onShadowToggle: (handler: ShadowToggleHandler) => Unsubscribe;
};

declare global {
  interface Window {
    desktop?: DesktopBridge;
    DesktopBridge?: DesktopBridge;
  }
}

const ALLOWED_EVENTS = new Set<DesktopSystemCheckChannel>([
  'system-check:open-panel',
  'system-check:initial-report',
  'system-check:initial-error',
  'system-check:report-missing',
  'system-check:report-error',
  'system-check:skipped',
]);

const noop: Unsubscribe = () => undefined;

function subscribe(channel: DesktopSystemCheckChannel, handler: SystemCheckHandler): Unsubscribe {
  if (!ALLOWED_EVENTS.has(channel) || typeof handler !== 'function') {
    return noop;
  }
  const listener = (_event: Electron.IpcRendererEvent, payload: unknown) => {
    try {
      handler(payload);
    } catch (error) {
      console.warn('[desktop] system-check handler threw', error);
    }
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

function exposeBridge() {
  const bridge: DesktopBridge = {
    runSystemCheck: (options) => ipcRenderer.invoke('system-check:run', options ?? {}),
    getLastSystemCheck: () => ipcRenderer.invoke('system-check:last'),
    openSystemCheckReport: async () => {
      const result = await ipcRenderer.invoke('system-check:open-report');
      return result as DesktopOpenReportResult;
    },
    exportSystemCheckReport: async (options) => {
      const result = await ipcRenderer.invoke('system-check:export-report', options ?? {});
      return result as DesktopExportDiagnosticsResult;
    },
    onSystemCheckEvent: (channel, handler) => subscribe(channel, handler),
    shadowCapture: (payload) => ipcRenderer.invoke('shadow:capture', payload ?? {}),
    indexSearch: (query) => ipcRenderer.invoke('index:search', query ?? ''),
    onShadowToggle: (handler) => {
      if (typeof handler !== 'function') {
        return noop;
      }
      const listener = () => {
        try {
          handler();
        } catch (error) {
          console.warn('[desktop] shadow toggle handler threw', error);
        }
      };
      ipcRenderer.on('desktop:shadow-toggle', listener);
      return () => {
        ipcRenderer.removeListener('desktop:shadow-toggle', listener);
      };
    },
  };

  contextBridge.exposeInMainWorld('desktop', bridge);
  contextBridge.exposeInMainWorld('DesktopBridge', bridge);
}

exposeBridge();
