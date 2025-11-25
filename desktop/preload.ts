import { contextBridge, ipcRenderer } from 'electron';
import { randomUUID } from 'node:crypto';

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
  sessionPartition?: string | null;
  isIncognito?: boolean;
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

type BrowserHistoryEntry = {
  id: number;
  url: string;
  title: string | null;
  visitTime: number;
  transition?: string | null;
  referrer?: string | null;
  tabId?: string;
};

type BrowserSettings = {
  thirdPartyCookies: boolean;
  searchMode: 'auto' | 'query';
  spellcheckLanguage: string;
  proxy: {
    mode: 'system' | 'manual';
    host?: string;
    port?: string;
  };
  openSearchExternally: boolean;
};

type BrowserAPI = {
  navigate: (url: string, options?: { tabId?: string }) => void;
  goBack: (options?: { tabId?: string }) => void;
  goForward: (options?: { tabId?: string }) => void;
  reload: (options?: { tabId?: string; ignoreCache?: boolean }) => void;
  createTab: (url?: string, options?: { incognito?: boolean }) => Promise<BrowserNavState>;
  closeTab: (tabId: string) => Promise<{ ok: boolean }>;
  setActiveTab: (tabId: string) => void;
  setBounds: (bounds: BrowserBounds) => void;
  onNavState: (handler: (state: BrowserNavState) => void) => Unsubscribe;
  onTabList: (handler: (summary: BrowserTabList) => void) => Unsubscribe;
  requestTabList: () => Promise<BrowserTabList>;
  onHistoryEntry: (handler: (entry: BrowserHistoryEntry) => void) => Unsubscribe;
  requestHistory: (limit?: number) => Promise<BrowserHistoryEntry[]>;
  onSettings: (handler: (settings: BrowserSettings) => void) => Unsubscribe;
  getSettings: () => Promise<BrowserSettings>;
  updateSettings: (patch: Partial<BrowserSettings>) => Promise<BrowserSettings>;
  getSpellcheckLanguages: () => Promise<string[]>;
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
  tabId?: string | null;
};

type LlmFramePayload = {
  requestId?: string | null;
  frame: string;
};

type LlmBridge = {
  stream: (payload: LlmStreamPayload) => Promise<unknown>;
  onFrame: (handler: (payload: LlmFramePayload) => void) => Unsubscribe;
  abort: (payload?: { requestId?: string | null; tabId?: string | null } | string | null) => Promise<unknown>;
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

type ModelRef = {
  name: string;
};

type AppConfig = {
  models_primary: ModelRef;
  models_fallback: ModelRef;
  models_embedder: ModelRef;
  features_shadow_mode: boolean;
  features_agent_mode: boolean;
  features_local_discovery: boolean;
  features_browsing_fallbacks: boolean;
  features_index_auto_rebuild: boolean;
  features_auth_clearance_detectors: boolean;
  chat_use_page_context_default: boolean;
  browser_persist: boolean;
  browser_allow_cookies: boolean;
  sources_seed: Record<string, unknown>;
  setup_completed: boolean;
  dev_render_loop_guard: boolean;
};

type ConfigFieldOption = {
  key: string;
  type: 'boolean' | 'select';
  label: string;
  description?: string;
  default: unknown;
  options?: string[] | null;
};

type ConfigSection = {
  id: string;
  label: string;
  fields: ConfigFieldOption[];
};

type ConfigSchema = {
  version: number;
  sections: ConfigSection[];
};

type HealthSnapshot = {
  status: string;
  timestamp: string;
  environment?: Record<string, unknown>;
  components: Record<string, { status: string; detail: Record<string, unknown> }>;
};

type ApiBridge = {
  config: {
    get: () => Promise<AppConfig>;
    update: (patch: Partial<AppConfig>) => Promise<{ ok: boolean }>;
    schema: () => Promise<ConfigSchema>;
  };
  health: () => Promise<HealthSnapshot>;
  capabilities: () => Promise<Record<string, unknown>>;
  diagnostics: {
    snapshot: () => Promise<Record<string, unknown>>;
    repair: () => Promise<Record<string, unknown>>;
  };
  models: {
    install: (models: string[]) => Promise<{ ok: boolean; results?: unknown; error?: string }>;
  };
};

declare global {
  interface Window {
    desktop?: DesktopBridge;
    DesktopBridge?: DesktopBridge;
    browserAPI?: BrowserAPI;
    llm?: LlmBridge;
    api?: ApiBridge;
  }
}

type CorrelatedPayload = Record<string, unknown> & { correlationId: string };

function ensureCorrelationPayload(payload?: Record<string, unknown> | null): CorrelatedPayload {
  const base: Record<string, unknown> =
    payload && typeof payload === 'object' ? { ...payload } : Object.create(null);
  const raw = typeof base.correlationId === 'string' ? base.correlationId.trim() : '';
  const correlationId = raw || randomUUID();
  base.correlationId = correlationId;
  return base as CorrelatedPayload;
}

const DEFAULT_API_URL = 'http://127.0.0.1:5050';

function resolveApiBase(): string {
  const explicit =
    process.env.API_URL || process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  if (typeof explicit === 'string' && explicit.trim().length > 0) {
    return explicit.trim().replace(/\/$/, '');
  }
  const rawPort = process.env.BACKEND_PORT;
  const parsedPort = rawPort ? Number.parseInt(rawPort, 10) : NaN;
  if (Number.isFinite(parsedPort) && parsedPort > 0) {
    return `http://127.0.0.1:${parsedPort}`.replace(/\/$/, '');
  }
  return DEFAULT_API_URL;
}

const API_BASE_URL = resolveApiBase();

function buildApiUrl(path: string): string {
  if (path.startsWith('http')) {
    return path;
  }
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}

async function parseApiJson<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') ?? '';
  let payload: unknown = null;
  try {
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      const text = await response.text();
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message =
      (payload && typeof payload === 'object' && 'error' in (payload as Record<string, unknown>)
        ? (payload as { error?: unknown }).error
        : null) ||
      (payload && typeof payload === 'object' && 'message' in (payload as Record<string, unknown>)
        ? (payload as { message?: unknown }).message
        : null) ||
      `Request failed (${response.status})`;
    const error = new Error(typeof message === 'string' ? message : 'Request failed');
    (error as Error & { status?: number; details?: unknown }).status = response.status;
    (error as Error & { status?: number; details?: unknown }).details = payload;
    throw error;
  }
  return payload as T;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
  };
  if (init?.headers instanceof Headers) {
    init.headers.forEach((value, key) => {
      headers[key] = value;
    });
  } else if (init?.headers && typeof init.headers === 'object') {
    Object.assign(headers, init.headers as Record<string, string>);
  }
  headers['x-correlation-id'] = headers['x-correlation-id'] || randomUUID();
  const response = await fetch(buildApiUrl(path), {
    credentials: init?.credentials ?? 'include',
    ...init,
    headers,
  });
  return parseApiJson<T>(response);
}

function invokeWithCorrelation<T = unknown>(channel: string, payload?: Record<string, unknown> | null) {
  return ipcRenderer.invoke(channel, ensureCorrelationPayload(payload));
}

function sendWithCorrelation(channel: string, payload?: Record<string, unknown> | null): void {
  ipcRenderer.send(channel, ensureCorrelationPayload(payload));
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

const BROWSER_ALLOWED_CHANNELS = new Set(['nav:state', 'browser:tabs', 'browser:history', 'settings:state']);

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
      sendWithCorrelation('nav:navigate', {
        url: target,
        tabId: options?.tabId ?? null,
      });
    },
    goBack: (options) => {
      sendWithCorrelation('nav:back', {
        tabId: options?.tabId ?? null,
      });
    },
    goForward: (options) => {
      sendWithCorrelation('nav:forward', {
        tabId: options?.tabId ?? null,
      });
    },
    reload: (options) => {
      sendWithCorrelation('nav:reload', {
        tabId: options?.tabId ?? null,
        ignoreCache: options?.ignoreCache ?? false,
      });
    },
    createTab: (url, options) =>
      invokeWithCorrelation('browser:create-tab', {
        url,
        incognito: options?.incognito ?? false,
      }),
    closeTab: (tabId) => invokeWithCorrelation('browser:close-tab', { tabId }),
    setActiveTab: (tabId) => {
      if (typeof tabId === 'string' && tabId) {
        sendWithCorrelation('browser:set-active', { tabId });
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
      sendWithCorrelation('browser:bounds', payload);
    },
    onNavState: (handler) => subscribeBrowserChannel('nav:state', handler),
    onTabList: (handler) => subscribeBrowserChannel('browser:tabs', handler),
    requestTabList: () => invokeWithCorrelation('browser:request-tabs'),
    onHistoryEntry: (handler) => subscribeBrowserChannel('browser:history', handler),
    requestHistory: (limit) =>
      invokeWithCorrelation('browser:request-history', {
        limit: Number.isFinite(limit) ? Number(limit) : undefined,
      }),
    onSettings: (handler) => subscribeBrowserChannel('settings:state', handler),
    getSettings: () => invokeWithCorrelation('settings:get'),
    updateSettings: (patch) => invokeWithCorrelation('settings:update', patch ?? {}),
    getSpellcheckLanguages: () => invokeWithCorrelation('settings:list-spellcheck-languages'),
  };

  return api;
}

function exposeBridge() {
  const bridge: DesktopBridge = {
    runSystemCheck: (options) => invokeWithCorrelation('system-check:run', options ?? {}),
    getLastSystemCheck: () => invokeWithCorrelation('system-check:last'),
    openSystemCheckReport: async () => {
      const result = await invokeWithCorrelation('system-check:open-report');
      return result as DesktopOpenReportResult;
    },
    exportSystemCheckReport: async (options) => {
      const result = await invokeWithCorrelation('system-check:export-report', options ?? {});
      return result as DesktopExportDiagnosticsResult;
    },
    onSystemCheckEvent: (channel, handler) => subscribe(channel, handler),
    shadowCapture: (payload) => invokeWithCorrelation('shadow:capture', payload ?? {}),
    indexSearch: (query) => {
      const normalized = typeof query === 'string' ? query : '';
      return invokeWithCorrelation('index:search', { query: normalized });
    },
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
      const tabId =
        typeof payload.tabId === 'string' && payload.tabId.trim().length > 0
          ? payload.tabId.trim()
          : null;
      return invokeWithCorrelation('llm:stream', { requestId, body, tabId });
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
    abort: (payload?: { requestId?: string | null; tabId?: string | null } | string | null) => {
      if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
        const requestId =
          typeof payload.requestId === 'string' && payload.requestId.trim().length > 0
            ? payload.requestId.trim()
            : payload.requestId ?? null;
        const tabId =
          typeof payload.tabId === 'string' && payload.tabId.trim().length > 0
            ? payload.tabId.trim()
            : payload.tabId ?? null;
        return invokeWithCorrelation('llm:abort', { requestId, tabId });
      }
      if (typeof payload === 'string') {
        const trimmed = payload.trim();
        return invokeWithCorrelation('llm:abort', { requestId: trimmed || null });
      }
      if (payload === null || payload === undefined) {
        return invokeWithCorrelation('llm:abort', {});
      }
      return invokeWithCorrelation('llm:abort', { value: payload });
    },
  });
}

function exposeBrowserAPI() {
  const api = createBrowserAPI();
  contextBridge.exposeInMainWorld('browserAPI', api);
}

function exposeApiBridge() {
  const api: ApiBridge = {
    config: {
      get: () => apiRequest<AppConfig>('/api/config'),
      update: (patch) => apiRequest<{ ok: boolean }>('/api/config', { method: 'PUT', body: JSON.stringify(patch ?? {}) }),
      schema: () => apiRequest<ConfigSchema>('/api/config/schema'),
    },
    health: () => apiRequest<HealthSnapshot>('/api/health'),
    capabilities: () => apiRequest<Record<string, unknown>>('/api/capabilities'),
    diagnostics: {
      snapshot: () => apiRequest<Record<string, unknown>>('/api/dev/diag/snapshot'),
      repair: () => apiRequest<Record<string, unknown>>('/api/dev/diag/repair', { method: 'POST' }),
    },
    models: {
      install: (models: string[]) =>
        apiRequest<{ ok: boolean; results?: unknown; error?: string }>('/api/admin/install_models', {
          method: 'POST',
          body: JSON.stringify({ models: Array.isArray(models) ? models : [] }),
        }),
    },
  };
  contextBridge.exposeInMainWorld('api', api);
}

// Simple client-side logger exposed to renderer: forwards to backend ingestion
function exposeAppLogger() {
  const send = async (payload: Record<string, unknown> | Record<string, unknown>[]) => {
    try {
      const base = process.env.API_URL || process.env.BACKEND_URL || 'http://127.0.0.1:5050';
      const url = `${base.replace(/\/$/, '')}/api/logs`;
      // support optional test run id header
      const tr = (Array.isArray(payload) ? undefined : (payload as any)?.tr) || process.env.NEXT_PUBLIC_TEST_RUN_ID;
      await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(tr ? { 'x-test-run-id': String(tr) } : {}) },
        body: JSON.stringify(payload),
      });
    } catch (error) {
      // swallow network errors silently; app should not break over logging
      // eslint-disable-next-line no-console
      console.warn('[appLogger] failed to send log', error);
    }
  };

  contextBridge.exposeInMainWorld('appLogger', {
    log: (obj: Record<string, unknown>) => {
      try {
        if (!obj || typeof obj !== 'object') return;
        // best-effort lightweight sanitisation
  const payload: Record<string, unknown> = { src: 'frontend', ...obj };
  if (!('event' in payload) || payload['event'] == null) (payload as any)['event'] = 'ui.log';
  if (!('level' in payload) || payload['level'] == null) (payload as any)['level'] = 'INFO';
        void send(payload);
      } catch (error) {
        // ignore
      }
    },
  });
}

exposeAppLogger();

spoofNavigator();
exposeBridge();
exposeBrowserAPI();
exposeApiBridge();
