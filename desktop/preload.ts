import { contextBridge, ipcRenderer } from 'electron';

type BrowserNavError = {
  code?: number;
  description?: string;
};

type BrowserNavState = {
  tabId: string;
  url: string;
  canGoBack: boolean;
  canGoForward: boolean;
  title?: string | null;
  favicon?: string | null;
  isActive: boolean;
  isLoading?: boolean;
  error?: BrowserNavError | null;
};

type BrowserTabList = {
  tabs: BrowserNavState[];
  activeTabId: string | null;
};

type BrowserBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type BrowserAPI = {
  navigate: (url: string, options?: { tabId?: string }) => void;
  goBack: (options?: { tabId?: string }) => void;
  goForward: (options?: { tabId?: string }) => void;
  reload: (options?: { tabId?: string; ignoreCache?: boolean }) => void;
  createTab: (url?: string) => Promise<BrowserNavState>;
  closeTab: (tabId: string) => Promise<{ ok: boolean }>;
  setActiveTab: (tabId: string) => void;
  setBounds: (bounds: BrowserBounds) => void;
  onNavState: (handler: (state: BrowserNavState) => void) => Unsubscribe;
  onTabList: (handler: (summary: BrowserTabList) => void) => Unsubscribe;
  requestTabList: () => Promise<BrowserTabList>;
};

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

type LlmStreamPayload = {
  requestId: string;
  body: Record<string, unknown>;
};

type LlmFramePayload = {
  requestId?: string | null;
  frame: string;
};

type LlmBridge = {
  stream: (payload: LlmStreamPayload) => Promise<unknown>;
  onFrame: (handler: (payload: LlmFramePayload) => void) => Unsubscribe;
  abort: (requestId?: string | null) => Promise<unknown>;
};

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
    browserAPI?: BrowserAPI;
    llm?: LlmBridge;
  }
}

function spoofNavigator(): void {
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.webdriver', error);
  }

  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.languages', error);
  }

  try {
    class FakePluginArray extends Array<{
      name: string;
      filename: string;
      description: string;
    }> {
      item(index: number) {
        return this[index] ?? null;
      }

      namedItem(name: string) {
        return this.find((plugin) => plugin.name === name) ?? null;
      }

      refresh() {
        // no-op
      }
    }

    const fakePlugins = new FakePluginArray(
      {
        name: 'Chrome PDF Viewer',
        filename: 'internal-pdf-viewer',
        description: 'Portable Document Format',
      },
      {
        name: 'Chromium PDF Viewer',
        filename: 'internal-pdf-viewer',
        description: 'Portable Document Format',
      },
      {
        name: 'Microsoft Edge PDF Viewer',
        filename: 'internal-pdf-viewer',
        description: 'Portable Document Format',
      },
    );

    Object.freeze(fakePlugins);

    Object.defineProperty(navigator, 'plugins', {
      get: () => fakePlugins,
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.plugins', error);
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

const BROWSER_ALLOWED_CHANNELS = new Set(['nav:state', 'browser:tabs']);

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

function subscribeBrowserChannel<T>(channel: string, handler: (payload: T) => void): Unsubscribe {
  if (!BROWSER_ALLOWED_CHANNELS.has(channel) || typeof handler !== 'function') {
    return noop;
  }
  const listener = (_event: Electron.IpcRendererEvent, payload: T) => {
    try {
      handler(payload);
    } catch (error) {
      console.warn(`[desktop] browser channel handler threw for ${channel}`, error);
    }
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

function createBrowserAPI(): BrowserAPI {
  const api: BrowserAPI = {
    navigate: (url, options) => {
      const target = typeof url === 'string' ? url.trim() : '';
      if (!target) {
        return;
      }
      ipcRenderer.send('nav:navigate', {
        url: target,
        tabId: options?.tabId ?? null,
      });
    },
    goBack: (options) => {
      ipcRenderer.send('nav:back', {
        tabId: options?.tabId ?? null,
      });
    },
    goForward: (options) => {
      ipcRenderer.send('nav:forward', {
        tabId: options?.tabId ?? null,
      });
    },
    reload: (options) => {
      ipcRenderer.send('nav:reload', {
        tabId: options?.tabId ?? null,
        ignoreCache: options?.ignoreCache ?? false,
      });
    },
    createTab: (url) => ipcRenderer.invoke('browser:create-tab', { url }),
    closeTab: (tabId) => ipcRenderer.invoke('browser:close-tab', { tabId }),
    setActiveTab: (tabId) => {
      if (typeof tabId === 'string' && tabId) {
        ipcRenderer.send('browser:set-active', tabId);
      }
    },
    setBounds: (bounds) => {
      if (!bounds || typeof bounds !== 'object') {
        return;
      }
      const payload: BrowserBounds = {
        x: Number.isFinite(bounds.x) ? Number(bounds.x) : 0,
        y: Number.isFinite(bounds.y) ? Number(bounds.y) : 0,
        width: Number.isFinite(bounds.width) ? Number(bounds.width) : 0,
        height: Number.isFinite(bounds.height) ? Number(bounds.height) : 0,
      };
      ipcRenderer.send('browser:bounds', payload);
    },
    onNavState: (handler) => subscribeBrowserChannel('nav:state', handler),
    onTabList: (handler) => subscribeBrowserChannel('browser:tabs', handler),
    requestTabList: () => ipcRenderer.invoke('browser:request-tabs'),
  };

  return api;
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
  contextBridge.exposeInMainWorld('llm', {
    stream: async (payload: LlmStreamPayload) => {
      if (!payload || typeof payload !== 'object') {
        throw new Error('stream payload required');
      }
      const requestId = typeof payload.requestId === 'string' ? payload.requestId.trim() : '';
      if (!requestId) {
        throw new Error('requestId is required');
      }
      const body = payload.body && typeof payload.body === 'object' ? payload.body : {};
      return ipcRenderer.invoke('llm:stream', { requestId, body });
    },
    onFrame: (handler: (payload: LlmFramePayload) => void) => {
      if (typeof handler !== 'function') {
        return noop;
      }
      const listener = (_event: Electron.IpcRendererEvent, data: LlmFramePayload) => {
        try {
          const framePayload = data && typeof data === 'object' ? data : { requestId: null, frame: '' };
          handler(framePayload);
        } catch (error) {
          console.warn('[llm] frame handler error', error);
        }
      };
      ipcRenderer.on('llm:frame', listener);
      return () => {
        ipcRenderer.removeListener('llm:frame', listener);
      };
    },
    abort: (requestId?: string | null) => ipcRenderer.invoke('llm:abort', { requestId: requestId ?? null }),
  });
}

function exposeBrowserAPI() {
  const api = createBrowserAPI();
  contextBridge.exposeInMainWorld('browserAPI', api);
}

spoofNavigator();
exposeBridge();
exposeBrowserAPI();
