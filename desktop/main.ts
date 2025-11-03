import {
  app,
  BrowserWindow,
  BrowserView,
  ipcMain,
  Menu,
  Rectangle,
  session,
  shell,
  WebContents,
} from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import log from 'electron-log';
import { randomUUID } from 'node:crypto';
import { TextDecoder } from 'node:util';

type BrowserDiagnosticsReport = Record<string, unknown> & {
  artifactPath?: string | null;
};

type SystemCheckResult = BrowserDiagnosticsReport | { skipped: true } | null;

type SystemCheckRunOptions = {
  timeoutMs?: number;
  write?: boolean;
};

type SystemCheckChannel =
  | 'system-check:open-panel'
  | 'system-check:initial-report'
  | 'system-check:initial-error'
  | 'system-check:report-missing'
  | 'system-check:report-error'
  | 'system-check:skipped';

type OpenReportResult = {
  ok: boolean;
  missing?: boolean;
  error?: string | null;
  path?: string | null;
};

type ExportReportResult = {
  ok: boolean;
  report?: BrowserDiagnosticsReport | null;
  artifactPath?: string | null;
  path?: string | null;
  error?: string | null;
  skipped?: boolean;
};

type BrowserNavError = {
  code?: number;
  description?: string;
};

type BrowserNavState = {
  tabId: string;
  url: string;
  title?: string | null;
  favicon?: string | null;
  canGoBack: boolean;
  canGoForward: boolean;
  isActive: boolean;
  isLoading: boolean;
  error?: BrowserNavError | null;
};

type BrowserTabList = {
  tabs: BrowserNavState[];
  activeTabId: string | null;
};

type BrowserTabRecord = {
  id: string;
  view: BrowserView;
  title: string | null;
  favicon?: string | null;
  lastUrl: string;
  isLoading: boolean;
  lastError?: BrowserNavError | null;
};

type BrowserBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

const require = createRequire(import.meta.url);
const { runBrowserDiagnostics }: {
  runBrowserDiagnostics: (options?: {
    timeoutMs?: number;
    write?: boolean;
    log?: boolean;
  }) => Promise<BrowserDiagnosticsReport>;
} = require('../scripts/diagnoseBrowser.js');

const DEFAULT_FRONTEND_ORIGIN = (() => {
  const fallbackHost = 'localhost';
  const fallbackPort = '3100';
  const rawHost = process.env.FRONTEND_HOST;
  const host =
    typeof rawHost === 'string' && rawHost.trim().length > 0 ? rawHost.trim() : fallbackHost;
  const rawPort = process.env.FRONTEND_PORT;
  const parsedPort = rawPort ? Number.parseInt(rawPort, 10) : NaN;
  const port = Number.isFinite(parsedPort) && parsedPort > 0 ? String(parsedPort) : fallbackPort;
  const protocol =
    process.env.FRONTEND_PROTOCOL?.trim().toLowerCase() === 'https' ? 'https' : 'http';
  return `${protocol}://${host}:${port}`;
})();
const DEFAULT_API_URL = 'http://127.0.0.1:5050';
const FRONTEND_URL = process.env.APP_URL || process.env.FRONTEND_URL || DEFAULT_FRONTEND_ORIGIN;
const API_BASE_URL = (() => {
  const explicit =
    process.env.API_URL || process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit && typeof explicit === 'string' && explicit.trim().length > 0) {
    return explicit.trim().replace(/\/$/, '');
  }
  const port = typeof process.env.BACKEND_PORT === 'string' ? process.env.BACKEND_PORT.trim() : '';
  if (port) {
    return `http://127.0.0.1:${port}`.replace(/\/$/, '');
  }
  return DEFAULT_API_URL;
})();

const JSON_HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json' } as const;
const activeLlmStreams = new Map<number, { controller: AbortController; requestId: string }>();

function flushSseBuffer(target: WebContents, requestId: string, buffer: string): string {
  let working = buffer;
  let index = working.indexOf("\n\n");
  while (index !== -1) {
    const frame = working.slice(0, index);
    working = working.slice(index + 2);
    if (frame.trim()) {
      target.send('llm:frame', { requestId, frame });
    }
    index = working.indexOf("\n\n");
  }
  return working;
}

function sendSseError(target: WebContents, requestId: string, payload: Record<string, unknown>) {
  target.send('llm:frame', {
    requestId,
    frame: `data: ${JSON.stringify(payload)}\n\n`,
  });
}

const isDev = !app.isPackaged;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

app.setAppLogsPath();

const MAIN_SESSION_KEY = 'persist:main';
const DESKTOP_USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const RESOLVED_USER_AGENT = (() => {
  const candidate = process.env.DESKTOP_USER_AGENT;
  if (typeof candidate === 'string') {
    const trimmed = candidate.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
  }
  return DESKTOP_USER_AGENT;
})();
const DEFAULT_TAB_URL = 'https://wikipedia.org';
const DEFAULT_TAB_TITLE = 'New Tab';
const DEFAULT_BOUNDS: Rectangle = { x: 0, y: 136, width: 1280, height: 720 };
const NAV_STATE_CHANNEL = 'nav:state';
const TAB_LIST_CHANNEL = 'browser:tabs';

let win: BrowserWindow | null = null;
let lastSystemCheck: SystemCheckResult = null;
let initialSystemCheckPromise: Promise<SystemCheckResult> | null = null;

const tabs = new Map<string, BrowserTabRecord>();
const tabOrder: string[] = [];
let activeTabId: string | null = null;
let browserContentBounds: Rectangle = { ...DEFAULT_BOUNDS };

function resolveFrontendTarget(): string {
  if (isDev) {
    return FRONTEND_URL;
  }
  if (/^https?:\/\//i.test(FRONTEND_URL)) {
    return FRONTEND_URL;
  }
  const candidates = [
    path.join(process.resourcesPath, 'frontend', 'index.html'),
    path.join(process.resourcesPath, 'frontend', 'out', 'index.html'),
    path.join(process.resourcesPath, 'frontend', 'dist', 'index.html'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return pathToFileURL(candidate).toString();
    }
  }
  const fallback = path.join(process.resourcesPath, 'frontend', 'index.html');
  if (fs.existsSync(fallback)) {
    return pathToFileURL(fallback).toString();
  }
  return FRONTEND_URL;
}

function resolveDiagnosticsPath(): string {
  return path.resolve(__dirname, '..', 'diagnostics', 'browser_diagnostics.json');
}

function notifyRenderer(channel: SystemCheckChannel | 'desktop:shadow-toggle', payload?: unknown) {
  const target = getMainWindow();
  target?.webContents.send(channel, payload);
}

function getMainWindow(): BrowserWindow | null {
  if (win && !win.isDestroyed()) {
    return win;
  }
  return null;
}

function sendToRenderer(channel: string, payload: unknown) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  target.webContents.send(channel, payload);
}

async function safeJson<T = unknown>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function getActiveTab(): BrowserTabRecord | undefined {
  if (!activeTabId) {
    return undefined;
  }
  return tabs.get(activeTabId);
}

function buildNavState(tab: BrowserTabRecord): BrowserNavState {
  const wc = tab.view.webContents;
  const currentUrl = wc.getURL() || tab.lastUrl || 'about:blank';
  return {
    tabId: tab.id,
    url: currentUrl,
    title: tab.title ?? null,
    favicon: tab.favicon ?? null,
    canGoBack: wc.canGoBack(),
    canGoForward: wc.canGoForward(),
    isActive: activeTabId === tab.id,
    isLoading: tab.isLoading,
    error: tab.lastError ?? null,
  };
}

function emitNavState(tab: BrowserTabRecord) {
  sendToRenderer(NAV_STATE_CHANNEL, buildNavState(tab));
}

function snapshotTabList(): BrowserTabList {
  const list: BrowserNavState[] = [];
  for (const id of tabOrder) {
    const tab = tabs.get(id);
    if (tab) {
      list.push(buildNavState(tab));
    }
  }
  return {
    tabs: list,
    activeTabId,
  };
}

function emitTabList() {
  sendToRenderer(TAB_LIST_CHANNEL, snapshotTabList());
}

function sanitizeBounds(bounds: BrowserBounds): Rectangle {
  const safe: Rectangle = {
    x: Number.isFinite(bounds.x) ? Math.max(0, Math.round(bounds.x)) : 0,
    y: Number.isFinite(bounds.y) ? Math.max(0, Math.round(bounds.y)) : 0,
    width: Number.isFinite(bounds.width) ? Math.max(0, Math.round(bounds.width)) : 0,
    height: Number.isFinite(bounds.height) ? Math.max(0, Math.round(bounds.height)) : 0,
  };

  if ((safe.width === 0 || safe.height === 0) && getMainWindow()) {
    const content = getMainWindow()!.getContentBounds();
    if (safe.width === 0) {
      safe.width = Math.max(0, content.width - safe.x);
    }
    if (safe.height === 0) {
      safe.height = Math.max(0, content.height - safe.y);
    }
  }

  if (safe.width === 0) {
    safe.width = DEFAULT_BOUNDS.width;
  }
  if (safe.height === 0) {
    safe.height = DEFAULT_BOUNDS.height;
  }
  return safe;
}

function applyBoundsToView(view: BrowserView) {
  const bounds = browserContentBounds;
  view.setBounds(bounds);
  view.setAutoResize({ width: true, height: true });
}

function updateBrowserBounds(bounds: BrowserBounds) {
  browserContentBounds = sanitizeBounds(bounds);
  const active = getActiveTab();
  if (active) {
    applyBoundsToView(active.view);
  }
}

function attachTab(tab: BrowserTabRecord) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  try {
    target.setBrowserView(tab.view);
    applyBoundsToView(tab.view);
    tab.view.webContents.focus();
  } catch (error) {
    log.warn('Failed to attach BrowserView', { tabId: tab.id, error });
  }
}

function detachTab(tab: BrowserTabRecord) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  try {
    target.removeBrowserView(tab.view);
  } catch (error) {
    log.warn('Failed to detach BrowserView', { tabId: tab.id, error });
  }
}

function setActiveTab(tabId: string) {
  const next = tabs.get(tabId);
  if (!next) {
    return;
  }

  if (activeTabId === tabId) {
    attachTab(next);
    emitNavState(next);
    emitTabList();
    return;
  }

  const previous = getActiveTab();
  if (previous) {
    detachTab(previous);
  }

  activeTabId = tabId;
  attachTab(next);
  emitNavState(next);
  emitTabList();
}

function ensureTabOrder(tabId: string) {
  if (!tabOrder.includes(tabId)) {
    tabOrder.push(tabId);
  }
}

function resolveTabFromId(tabId: unknown): BrowserTabRecord | undefined {
  if (typeof tabId === 'string' && tabId) {
    return tabs.get(tabId);
  }
  return getActiveTab();
}

function handleTabLifecycle(tab: BrowserTabRecord) {
  const { webContents: wc } = tab.view;

  wc.setWindowOpenHandler(({ url }) => {
    if (typeof url === 'string' && url.trim().length > 0) {
      void createBrowserTab(url, { activate: true });
    }
    return { action: 'deny' };
  });

  wc.on('did-start-navigation', (_event, url, _isInPlace, isMainFrame) => {
    if (!isMainFrame) {
      return;
    }
    tab.isLoading = true;
    tab.lastError = null;
    tab.lastUrl = url;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-navigate', (_event, url) => {
    tab.lastUrl = url;
    tab.isLoading = false;
    tab.lastError = null;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-navigate-in-page', (_event, url) => {
    tab.lastUrl = url;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-stop-loading', () => {
    if (tab.isLoading) {
      tab.isLoading = false;
      emitNavState(tab);
      emitTabList();
    }
  });

  wc.on('page-title-updated', (_event, title) => {
    tab.title = title || DEFAULT_TAB_TITLE;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('page-favicon-updated', (_event, favicons) => {
    tab.favicon = Array.isArray(favicons) && favicons.length > 0 ? favicons[0] ?? null : null;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-fail-load', (_event, errorCode, errorDescription, _validatedURL, isMainFrame) => {
    if (!isMainFrame || errorCode === -3) {
      return;
    }
    tab.isLoading = false;
    tab.lastError = {
      code: errorCode,
      description: errorDescription || 'Navigation failed',
    };
    emitNavState(tab);
    emitTabList();
  });
}

async function createBrowserTab(url?: string, options: { activate?: boolean } = {}): Promise<BrowserNavState> {
  const id = randomUUID();
  const view = new BrowserView({
    webPreferences: {
      partition: MAIN_SESSION_KEY ?? 'persist:main',
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      webviewTag: true,
    },
  });

  view.webContents.setUserAgent(RESOLVED_USER_AGENT);

  const tab: BrowserTabRecord = {
    id,
    view,
    title: DEFAULT_TAB_TITLE,
    favicon: null,
    lastUrl: DEFAULT_TAB_URL,
    isLoading: false,
    lastError: null,
  };

  tabs.set(id, tab);
  ensureTabOrder(id);
  handleTabLifecycle(tab);

  if (options.activate !== false) {
    setActiveTab(id);
  }

  const targetUrl = typeof url === 'string' && url.trim().length > 0 ? url.trim() : DEFAULT_TAB_URL;
  tab.lastUrl = targetUrl;
  tab.isLoading = true;
  emitNavState(tab);
  emitTabList();

  try {
    await view.webContents.loadURL(targetUrl);
  } catch (error) {
    log.warn('Failed to load tab URL', { url: targetUrl, error });
    tab.isLoading = false;
    tab.lastError = {
      description: error instanceof Error ? error.message : String(error),
    };
    emitNavState(tab);
  }

  return buildNavState(tab);
}

function closeBrowserTab(tabId: string): boolean {
  const tab = tabs.get(tabId);
  if (!tab) {
    return false;
  }

  const index = tabOrder.indexOf(tabId);
  if (index >= 0) {
    tabOrder.splice(index, 1);
  }

  const wasActive = activeTabId === tabId;
  if (wasActive) {
    detachTab(tab);
  }

  tabs.delete(tabId);

  try {
    if (!tab.view.webContents.isDestroyed()) {
      tab.view.webContents.removeAllListeners();
      tab.view.webContents.stop();
    }
  } catch (error) {
    log.warn('Failed to destroy BrowserView webContents', { tabId, error });
  }

  if (wasActive) {
    activeTabId = null;
    const fallbackId = tabOrder[index] ?? tabOrder[index - 1] ?? tabOrder[0] ?? null;
    if (fallbackId) {
      setActiveTab(fallbackId);
    }
  }

  if (tabOrder.length === 0) {
    void createBrowserTab(DEFAULT_TAB_URL, { activate: true }).catch((error) => {
      log.error('Failed to create fallback tab', error);
    });
  } else {
    emitTabList();
  }

  return true;
}

async function runBrowserSystemCheck(options: SystemCheckRunOptions = {}): Promise<SystemCheckResult> {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    lastSystemCheck = { skipped: true };
    return lastSystemCheck;
  }
  await app.whenReady();
  const runOptions: { timeoutMs?: number; write?: boolean; log?: boolean } = { log: false };
  if (typeof options.timeoutMs === 'number' && Number.isFinite(options.timeoutMs)) {
    runOptions.timeoutMs = options.timeoutMs;
  }
  if (options.write === false) {
    runOptions.write = false;
  }
  const report = await runBrowserDiagnostics(runOptions);
  lastSystemCheck = report ?? null;
  return lastSystemCheck;
}

function ensureInitialSystemCheck(): Promise<SystemCheckResult> {
  if (initialSystemCheckPromise) {
    return initialSystemCheckPromise;
  }
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    lastSystemCheck = { skipped: true };
    initialSystemCheckPromise = Promise.resolve(lastSystemCheck);
    return initialSystemCheckPromise;
  }
  initialSystemCheckPromise = (async () => {
    try {
      return await runBrowserSystemCheck({});
    } catch (error) {
      log.warn('Browser diagnostics failed', error);
      throw error instanceof Error ? error : new Error(String(error));
    }
  })();
  return initialSystemCheckPromise;
}

async function openSystemCheckReport(): Promise<OpenReportResult> {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { ok: false, missing: true };
  }
  const outputPath = resolveDiagnosticsPath();
  if (!fs.existsSync(outputPath)) {
    return { ok: false, missing: true };
  }
  const error = await shell.openPath(outputPath);
  if (error) {
    return { ok: false, error, path: outputPath };
  }
  return { ok: true, path: outputPath };
}

async function exportSystemCheckReport(options: SystemCheckRunOptions = {}): Promise<ExportReportResult> {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { ok: false, skipped: true };
  }
  try {
    const report = await runBrowserSystemCheck(options);
    const artifactPath =
      report && typeof report === 'object' && 'artifactPath' in report
        ? (report.artifactPath as string | null | undefined) ?? null
        : null;
    return {
      ok: true,
      report,
      artifactPath,
      path: artifactPath ?? null,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, error: message };
  }
}

function buildApplicationMenu() {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'Browser',
      submenu: [
        {
          label: 'Toggle Shadow Mode',
          click: () => notifyRenderer('desktop:shadow-toggle'),
        },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Run System Check…',
          click: () => notifyRenderer('system-check:open-panel'),
        },
        {
          label: 'Open System Check Report',
          click: async () => {
            const result = await openSystemCheckReport();
            if (!result.ok) {
              if (result.missing) {
                notifyRenderer('system-check:report-missing');
              } else if (result.error) {
                notifyRenderer('system-check:report-error', result.error);
              }
            }
          },
        },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function createWindow() {
  win = new BrowserWindow({
    width: 1366,
    height: 900,
    show: false,
    title: 'Personal Search Engine',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      partition: MAIN_SESSION_KEY ?? 'persist:main',
      webviewTag: true,
      spellcheck: true,
    },
  });

  win.once('ready-to-show', () => win?.show());

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      void createBrowserTab(url, { activate: true });
    }
    return { action: 'deny' };
  });

  win.on('resize', () => {
    const active = getActiveTab();
    if (active) {
      applyBoundsToView(active.view);
    }
  });

  const target = resolveFrontendTarget();
  win
    .loadURL(target)
    .catch((error) => {
      log.error('Failed to load frontend', error);
    });

  win.on('closed', () => {
    for (const [tabId, tab] of tabs) {
      try {
        if (!tab.view.webContents.isDestroyed()) {
          tab.view.webContents.removeAllListeners();
          tab.view.webContents.stop();
        }
      } catch (error) {
        log.warn('Failed to clean up tab during window close', { tabId, error });
      }
    }
    tabs.clear();
    tabOrder.splice(0, tabOrder.length);
    activeTabId = null;
    win = null;
  });
}

app.whenReady().then(async () => {
  const mainSession = session.fromPartition(MAIN_SESSION_KEY);
  mainSession.setUserAgent(RESOLVED_USER_AGENT);

  mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const acceptLanguageHeader =
      details.requestHeaders['Accept-Language'] ??
      details.requestHeaders['accept-language'];

    const hintKeys = [
      'sec-ch-ua',
      'sec-ch-ua-mobile',
      'sec-ch-ua-platform',
      'sec-ch-ua-arch',
      'sec-ch-ua-model',
      'sec-ch-ua-platform-version',
      'sec-ch-ua-full-version-list',
    ];

    const headers = {
      ...details.requestHeaders,
      'User-Agent': RESOLVED_USER_AGENT,
    };

    if (acceptLanguageHeader) {
      headers['Accept-Language'] = acceptLanguageHeader;
    }

    for (const key of hintKeys) {
      const value =
        details.requestHeaders[key] ?? details.requestHeaders[key.toUpperCase()];
      if (value != null) {
        headers[key] = value;
      }
    }

    headers['sec-ch-ua'] =
      headers['sec-ch-ua'] ??
      '"Chromium";v="120", "Not A(Brand";v="99"';
    headers['sec-ch-ua-mobile'] =
      headers['sec-ch-ua-mobile'] ?? '?0';
    headers['sec-ch-ua-platform'] =
      headers['sec-ch-ua-platform'] ?? '"macOS"';

    if (!headers['Accept-Language']) {
      headers['Accept-Language'] = runtimeNetworkState.acceptLanguage || app.getLocale();
    }

    callback({ requestHeaders: headers });
  });

  mainSession.webRequest.onHeadersReceived((details, callback) => {
    const headers = details.responseHeaders || {};
    if (isDev) {
      headers['Content-Security-Policy'] = [
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http: https:",
      ];
    }
    callback({ responseHeaders: headers });
  });

  buildApplicationMenu();
  createWindow();
  browserContentBounds = sanitizeBounds(browserContentBounds);
  if (!tabs.size) {
    await createBrowserTab(DEFAULT_TAB_URL, { activate: true });
  }

  const initialCheck = ensureInitialSystemCheck();
  initialCheck
    .then((result) => {
      if (!win || win.isDestroyed()) {
        return;
      }
      if (result && 'skipped' in result) {
        notifyRenderer('system-check:skipped');
      } else if (result) {
        notifyRenderer('system-check:initial-report', result);
      }
    })
    .catch((error) => {
      if (!win || win.isDestroyed()) {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      notifyRenderer('system-check:initial-error', message);
    });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle(
  'llm:stream',
  async (
    event,
    payload: { requestId?: string | null; body?: Record<string, unknown> | null } | undefined,
  ) => {
    const sender = event.sender;
    const contentsId = sender.id;
    const baseId = typeof payload?.requestId === 'string' ? payload.requestId.trim() : '';
    const requestId = baseId || randomUUID();
    const rawBody = payload?.body && typeof payload.body === 'object' ? payload.body : {};
    const body: Record<string, unknown> = { ...(rawBody as Record<string, unknown>) };
    if (typeof body['request_id'] !== 'string') {
      body['request_id'] = requestId;
    }
    body['stream'] = true;

    const controller = new AbortController();
    const existing = activeLlmStreams.get(contentsId);
    if (existing) {
      existing.controller.abort();
    }
    activeLlmStreams.set(contentsId, { controller, requestId });

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { ...JSON_HEADERS, Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        sendSseError(sender, requestId, {
          type: 'error',
          error: response.ok ? 'stream_unavailable' : `http_${response.status}`,
          status: response.status,
        });
        return { ok: false, status: response.status };
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        buffer = flushSseBuffer(sender, requestId, buffer);
      }
      buffer += decoder.decode();
      flushSseBuffer(sender, requestId, buffer);
      return { ok: true };
    } catch (error) {
      const aborted = controller.signal.aborted;
      const message = error instanceof Error ? error.message : String(error ?? 'stream_failed');
      sendSseError(sender, requestId, {
        type: 'error',
        error: aborted ? 'aborted' : message,
      });
      return { ok: false, error: message, aborted };
    } finally {
      const entry = activeLlmStreams.get(contentsId);
      if (entry && entry.requestId === requestId) {
        activeLlmStreams.delete(contentsId);
      }
    }
  },
);

ipcMain.handle(
  'llm:abort',
  (event, payload: { requestId?: string | null } | string | null | undefined) => {
    const contentsId = event.sender.id;
    const entry = activeLlmStreams.get(contentsId);
    if (!entry) {
      return { ok: false, active: false };
    }
    const requestId =
      typeof payload === 'string' || payload === null
        ? payload
        : payload && typeof payload === 'object'
          ? payload.requestId ?? null
          : null;
    if (requestId && requestId !== entry.requestId) {
      return { ok: false, mismatch: true };
    }
    entry.controller.abort();
    activeLlmStreams.delete(contentsId);
    return { ok: true };
  },
);

ipcMain.handle('shadow:capture', async (_evt, payload) => {
  try {
    const response = await fetch(`${API_BASE_URL}/api/shadow/snapshot`, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(payload ?? {}),
    });
    return {
      ok: response.ok,
      status: response.status,
      data: await safeJson(response),
    };
  } catch (error: unknown) {
    log.error('shadow:capture failed', error);
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
});

ipcMain.handle('browser:create-tab', async (_event, payload: { url?: string } | undefined) => {
  const url = typeof payload?.url === 'string' ? payload.url : undefined;
  return createBrowserTab(url, { activate: true });
});

ipcMain.handle('browser:close-tab', async (_event, payload: { tabId?: string } | undefined) => {
  const tabId = typeof payload?.tabId === 'string' ? payload.tabId : '';
  return { ok: tabId ? closeBrowserTab(tabId) : false };
});

ipcMain.handle('browser:request-tabs', async () => snapshotTabList());

ipcMain.on('browser:set-active', (_event, tabId: unknown) => {
  if (typeof tabId === 'string' && tabId) {
    setActiveTab(tabId);
  }
});

ipcMain.on('browser:bounds', (_event, bounds: BrowserBounds) => {
  if (bounds && typeof bounds === 'object') {
    updateBrowserBounds(bounds);
  }
});

ipcMain.on('nav:navigate', (_event, payload: { url?: string; tabId?: string | null } | undefined) => {
  const url = typeof payload?.url === 'string' ? payload.url.trim() : '';
  if (!url) {
    return;
  }
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  tab.lastError = null;
  tab.lastUrl = url;
  emitNavState(tab);
  void tab.view.webContents.loadURL(url).catch((error) => {
    log.warn('Failed to navigate tab', { tabId: tab.id, url, error });
    tab.isLoading = false;
    tab.lastError = {
      description: error instanceof Error ? error.message : String(error),
    };
    emitNavState(tab);
  });
});

ipcMain.on('nav:back', (_event, payload: { tabId?: string | null } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoBack()) {
    tab.view.webContents.goBack();
  }
  emitNavState(tab);
});

ipcMain.on('nav:forward', (_event, payload: { tabId?: string | null } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoForward()) {
    tab.view.webContents.goForward();
  }
  emitNavState(tab);
});

ipcMain.on('nav:reload', (_event, payload: { tabId?: string | null; ignoreCache?: boolean } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  try {
    if (payload?.ignoreCache) {
      tab.view.webContents.reloadIgnoringCache();
    } else {
      tab.view.webContents.reload();
    }
  } catch (error) {
    log.warn('Failed to reload tab', { tabId: tab.id, error });
    tab.isLoading = false;
  }
  emitNavState(tab);
});

ipcMain.handle('index:search', async (_evt, query: string) => {
  try {
    const url = new URL(`${API_BASE_URL}/api/index/search`);
    if (typeof query === 'string' && query.trim().length > 0) {
      url.searchParams.set('q', query);
    }
    const response = await fetch(url);
    return {
      ok: response.ok,
      status: response.status,
      data: await safeJson(response),
    };
  } catch (error: unknown) {
    log.error('index:search failed', error);
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
});

ipcMain.handle('system-check:run', async (_event, rawOptions = {}) => {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { skipped: true };
  }
  const options: SystemCheckRunOptions = {};
  if (typeof rawOptions.timeoutMs === 'number' && Number.isFinite(rawOptions.timeoutMs)) {
    options.timeoutMs = rawOptions.timeoutMs;
  }
  if (rawOptions.write === false) {
    options.write = false;
  }
  try {
    const report = await runBrowserSystemCheck(options);
    return report ?? null;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    log.warn('system-check:run failed', message);
    throw error instanceof Error ? error : new Error(message);
  }
});

ipcMain.handle('system-check:last', async () => {
  try {
    await ensureInitialSystemCheck();
  } catch (error) {
    log.warn('system-check:last initial check failed', error);
  }
  return lastSystemCheck;
});

ipcMain.handle('system-check:open-report', async () => openSystemCheckReport());

ipcMain.handle('system-check:export-report', async (_event, rawOptions = {}) => {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { ok: false, skipped: true };
  }
  const options: SystemCheckRunOptions = {};
  if (typeof rawOptions.timeoutMs === 'number' && Number.isFinite(rawOptions.timeoutMs)) {
    options.timeoutMs = rawOptions.timeoutMs;
  }
  if (rawOptions.write === false) {
    options.write = false;
  }
  return exportSystemCheckReport(options);
});
