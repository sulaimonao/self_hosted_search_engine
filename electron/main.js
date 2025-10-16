const {
  app,
  BrowserWindow,
  BrowserView,
  shell,
  Menu,
  ipcMain,
  session,
} = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const { randomUUID } = require('crypto');

const { runBrowserDiagnostics } = require('../scripts/diagnoseBrowser');

const DEFAULT_FRONTEND_URL = 'http://localhost:3100';
const FRONTEND_URL = process.env.FRONTEND_URL || DEFAULT_FRONTEND_URL;
const DEFAULT_API_URL = 'http://127.0.0.1:5050';
const API_BASE_URL = (() => {
  const explicit =
    process.env.API_URL ||
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit && typeof explicit === 'string' && explicit.trim().length > 0) {
    return explicit.trim().replace(/\/$/, '');
  }
  const port = typeof process.env.BACKEND_PORT === 'string' ? process.env.BACKEND_PORT.trim() : '';
  if (port) {
    return `http://127.0.0.1:${port}`.replace(/\/$/, '');
  }
  return DEFAULT_API_URL;
})();
const JSON_HEADERS = { 'Content-Type': 'application/json', Accept: 'application/json' };

let mainWindow;
let lastBrowserDiagnostics = null;
let initialBrowserDiagnosticsPromise = null;

app.setAppLogsPath();

const MAIN_SESSION_KEY = 'persist:main';
const DESKTOP_USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.90 Safari/537.36';
const DEFAULT_TAB_URL = 'https://wikipedia.org';
const DEFAULT_TAB_TITLE = 'New Tab';
const DEFAULT_BOUNDS = { x: 0, y: 136, width: 1280, height: 720 };
const NAV_STATE_CHANNEL = 'nav:state';
const TAB_LIST_CHANNEL = 'browser:tabs';

const tabs = new Map();
const tabOrder = [];
let activeTabId = null;
let browserContentBounds = { ...DEFAULT_BOUNDS };

function resolveFrontendUrl() {
  if (!app.isPackaged) {
    return FRONTEND_URL;
  }

  if (/^https?:\/\//i.test(FRONTEND_URL)) {
    return FRONTEND_URL;
  }

  const appPath = app.getAppPath();
  const candidates = [
    path.join(appPath, 'frontend', 'out', 'index.html'),
    path.join(appPath, 'frontend', 'dist', 'index.html'),
  ];

  for (const entry of candidates) {
    if (fs.existsSync(entry)) {
      return pathToFileURL(entry).toString();
    }
  }

  return FRONTEND_URL;
}

function resolveDiagnosticsPath() {
  return path.resolve(__dirname, '..', 'diagnostics', 'browser_diagnostics.json');
}

function notifyRenderer(channel, payload) {
  const target = getMainWindow();
  if (target) {
    target.webContents.send(channel, payload);
  }
}

function getMainWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return mainWindow;
  }
  return null;
}

function sendToRenderer(channel, payload) {
  const target = getMainWindow();
  if (target) {
    target.webContents.send(channel, payload);
  }
}

function safeJson(response) {
  return response
    .json()
    .catch(() => null);
}

function getActiveTab() {
  if (!activeTabId) {
    return undefined;
  }
  return tabs.get(activeTabId);
}

function buildNavState(tab) {
  const wc = tab.view.webContents;
  const url = wc.getURL() || tab.lastUrl || 'about:blank';
  return {
    tabId: tab.id,
    url,
    title: tab.title ?? null,
    favicon: tab.favicon ?? null,
    canGoBack: wc.canGoBack(),
    canGoForward: wc.canGoForward(),
    isActive: activeTabId === tab.id,
    isLoading: tab.isLoading,
    error: tab.lastError ?? null,
  };
}

function snapshotTabList() {
  const list = [];
  for (const id of tabOrder) {
    const tab = tabs.get(id);
    if (tab) {
      list.push(buildNavState(tab));
    }
  }
  return { tabs: list, activeTabId };
}

function emitNavState(tab) {
  sendToRenderer(NAV_STATE_CHANNEL, buildNavState(tab));
}

function emitTabList() {
  sendToRenderer(TAB_LIST_CHANNEL, snapshotTabList());
}

function sanitizeBounds(bounds) {
  const safe = {
    x: Number.isFinite(bounds?.x) ? Math.max(0, Math.round(bounds.x)) : 0,
    y: Number.isFinite(bounds?.y) ? Math.max(0, Math.round(bounds.y)) : 0,
    width: Number.isFinite(bounds?.width) ? Math.max(0, Math.round(bounds.width)) : 0,
    height: Number.isFinite(bounds?.height) ? Math.max(0, Math.round(bounds.height)) : 0,
  };

  const window = getMainWindow();
  if (window && (safe.width === 0 || safe.height === 0)) {
    const { width, height } = window.getContentBounds();
    if (safe.width === 0) {
      safe.width = Math.max(0, width - safe.x);
    }
    if (safe.height === 0) {
      safe.height = Math.max(0, height - safe.y);
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

function applyBoundsToView(view) {
  view.setBounds(browserContentBounds);
  view.setAutoResize({ width: true, height: true });
}

function updateBrowserBounds(bounds) {
  browserContentBounds = sanitizeBounds(bounds);
  const active = getActiveTab();
  if (active) {
    applyBoundsToView(active.view);
  }
}

function attachTab(tab) {
  const window = getMainWindow();
  if (!window) {
    return;
  }
  try {
    window.setBrowserView(tab.view);
    applyBoundsToView(tab.view);
    tab.view.webContents.focus();
  } catch (error) {
    console.warn('Failed to attach BrowserView', { tabId: tab.id, error });
  }
}

function detachTab(tab) {
  const window = getMainWindow();
  if (!window) {
    return;
  }
  try {
    window.removeBrowserView(tab.view);
  } catch (error) {
    console.warn('Failed to detach BrowserView', { tabId: tab.id, error });
  }
}

function ensureTabOrder(tabId) {
  if (!tabOrder.includes(tabId)) {
    tabOrder.push(tabId);
  }
}

function resolveTabFromId(tabId) {
  if (typeof tabId === 'string' && tabId) {
    return tabs.get(tabId);
  }
  return getActiveTab();
}

function handleTabLifecycle(tab) {
  const wc = tab.view.webContents;

  wc.setWindowOpenHandler(({ url }) => {
    if (typeof url === 'string' && url.trim().length > 0) {
      void createBrowserTab(url, { activate: true });
    }
    return { action: 'deny' };
  });

  wc.on('did-start-navigation', (_event, url, _isInPlace, isMainFrame) => {
    if (!isMainFrame) return;
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

  wc.on('did-fail-load', (_event, errorCode, errorDescription, _url, isMainFrame) => {
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

async function createBrowserTab(url, options = {}) {
  const id = randomUUID();
  const view = new BrowserView({
    webPreferences: {
      partition: MAIN_SESSION_KEY,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });

  view.webContents.setUserAgent(DESKTOP_USER_AGENT);

  const tab = {
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
    console.warn('Failed to load tab URL', { url: targetUrl, error });
    tab.isLoading = false;
    tab.lastError = {
      description: error instanceof Error ? error.message : String(error),
    };
    emitNavState(tab);
  }

  return buildNavState(tab);
}

function setActiveTab(tabId) {
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

function closeBrowserTab(tabId) {
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
    console.warn('Failed to destroy BrowserView webContents', { tabId, error });
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
      console.error('Failed to create fallback tab', error);
    });
  } else {
    emitTabList();
  }

  return true;
}

ipcMain.handle('shadow:capture', async (_event, payload) => {
  try {
    const body = typeof payload === 'object' && payload !== null ? payload : {};
    const response = await fetch(`${API_BASE_URL}/api/shadow/snapshot`, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    const data = await safeJson(response);
    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  } catch (error) {
    console.error('shadow:capture failed', error);
    return { ok: false, error: error?.message || String(error) };
  }
});

ipcMain.handle('index:search', async (_event, query) => {
  try {
    const url = new URL(`${API_BASE_URL}/api/index/search`);
    if (typeof query === 'string' && query.trim().length > 0) {
      url.searchParams.set('q', query);
    }
    const response = await fetch(url.toString(), {
      headers: { Accept: 'application/json' },
    });
    const data = await safeJson(response);
    return {
      ok: response.ok,
      status: response.status,
      data,
    };
  } catch (error) {
    console.error('index:search failed', error);
    return { ok: false, error: error?.message || String(error) };
  }
});

async function runBrowserSystemCheck(options = {}) {
  if (!app.isReady()) {
    await app.whenReady();
  }
  const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : undefined;
  const report = await runBrowserDiagnostics({
    timeoutMs,
    write: options.write !== false,
    log: false,
  });
  lastBrowserDiagnostics = report;
  return report;
}

function ensureInitialDiagnostics() {
  if (initialBrowserDiagnosticsPromise) {
    return initialBrowserDiagnosticsPromise;
  }
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    initialBrowserDiagnosticsPromise = Promise.resolve(null);
    return initialBrowserDiagnosticsPromise;
  }
  initialBrowserDiagnosticsPromise = runBrowserSystemCheck({}).catch((error) => {
    console.warn('Browser diagnostics failed', error);
    return { error: error?.message || String(error) };
  });
  return initialBrowserDiagnosticsPromise;
}

function buildApplicationMenu() {
  const template = [];

  if (process.platform === 'darwin') {
    template.push({
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'services' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    });
  }

  template.push({
    label: 'File',
    submenu: process.platform === 'darwin' ? [{ role: 'close' }] : [{ role: 'quit' }],
  });

  template.push({
    label: 'View',
    submenu: [{ role: 'reload' }, { role: 'toggledevtools' }],
  });

  template.push({
    label: 'Help',
    submenu: [
      {
        label: 'Run System Check…',
        click: () => {
          notifyRenderer('system-check:open-panel');
        },
      },
      {
        label: 'Open System Check Report',
        click: async () => {
          const outputPath = resolveDiagnosticsPath();
          if (!fs.existsSync(outputPath)) {
            notifyRenderer('system-check:report-missing');
            return;
          }
          const error = await shell.openPath(outputPath);
          if (error) {
            notifyRenderer('system-check:report-error', error);
          }
        },
      },
    ],
  });

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function loadFrontend(win) {
  const target = resolveFrontendUrl();
  win.loadURL(target);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 900,
    title: 'Personal Search Engine',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      partition: MAIN_SESSION_KEY,
    },
  });

  win.once('ready-to-show', () => win.show());

  loadFrontend(win);

  win.webContents.on('did-fail-load', (_event, _code, _desc, _url, isMainFrame) => {
    if (isMainFrame) {
      setTimeout(() => loadFrontend(win), 800);
    }
  });

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

  win.on('closed', () => {
    for (const [tabId, tab] of tabs) {
      try {
        if (!tab.view.webContents.isDestroyed()) {
          tab.view.webContents.removeAllListeners();
          tab.view.webContents.stop();
        }
      } catch (error) {
        console.warn('Failed to clean up tab during window close', { tabId, error });
      }
    }
    tabs.clear();
    tabOrder.splice(0, tabOrder.length);
    activeTabId = null;
    if (mainWindow === win) {
      mainWindow = null;
    }
  });

  return win;
}

ipcMain.handle('system-check:run', async (_event, options = {}) => {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { skipped: true };
  }
  return runBrowserSystemCheck(options ?? {});
});

ipcMain.handle('system-check:last', async () => {
  await ensureInitialDiagnostics();
  return lastBrowserDiagnostics;
});

ipcMain.handle('system-check:open-report', async () => {
  const outputPath = resolveDiagnosticsPath();
  if (!fs.existsSync(outputPath)) {
    return { ok: false, missing: true };
  }
  const error = await shell.openPath(outputPath);
  return { ok: !error, error: error || null, path: outputPath };
});

ipcMain.handle('system-check:export-report', async (_event, options = {}) => {
  if (process.env.SKIP_SYSTEM_CHECK === '1') {
    return { ok: false, skipped: true };
  }
  try {
    const runOptions = {};
    if (typeof options.timeoutMs === 'number' && Number.isFinite(options.timeoutMs)) {
      runOptions.timeoutMs = options.timeoutMs;
    }
    if (options.write === false) {
      runOptions.write = false;
    }
    const report = await runBrowserSystemCheck(runOptions);
    const artifactPath = typeof report === 'object' && report ? report.artifactPath ?? null : null;
    return {
      ok: true,
      report,
      artifactPath,
      path: artifactPath ?? null,
    };
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }
});

ipcMain.handle('browser:create-tab', async (_event, payload = {}) => {
  const url = typeof payload.url === 'string' ? payload.url : undefined;
  return createBrowserTab(url, { activate: true });
});

ipcMain.handle('browser:close-tab', async (_event, payload = {}) => {
  const tabId = typeof payload.tabId === 'string' ? payload.tabId : '';
  return { ok: tabId ? closeBrowserTab(tabId) : false };
});

ipcMain.handle('browser:request-tabs', async () => snapshotTabList());

ipcMain.on('browser:set-active', (_event, tabId) => {
  if (typeof tabId === 'string' && tabId) {
    setActiveTab(tabId);
  }
});

ipcMain.on('browser:bounds', (_event, bounds) => {
  if (bounds && typeof bounds === 'object') {
    updateBrowserBounds(bounds);
  }
});

ipcMain.on('nav:navigate', (_event, payload = {}) => {
  const url = typeof payload.url === 'string' ? payload.url.trim() : '';
  if (!url) {
    return;
  }
  const tab = resolveTabFromId(payload.tabId);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  tab.lastError = null;
  tab.lastUrl = url;
  emitNavState(tab);
  tab.view.webContents
    .loadURL(url)
    .catch((error) => {
      console.warn('Failed to navigate tab', { tabId: tab.id, url, error });
      tab.isLoading = false;
      tab.lastError = {
        description: error instanceof Error ? error.message : String(error),
      };
      emitNavState(tab);
    });
});

ipcMain.on('nav:back', (_event, payload = {}) => {
  const tab = resolveTabFromId(payload.tabId);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoBack()) {
    tab.view.webContents.goBack();
  }
  emitNavState(tab);
});

ipcMain.on('nav:forward', (_event, payload = {}) => {
  const tab = resolveTabFromId(payload.tabId);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoForward()) {
    tab.view.webContents.goForward();
  }
  emitNavState(tab);
});

ipcMain.on('nav:reload', (_event, payload = {}) => {
  const tab = resolveTabFromId(payload.tabId);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  try {
    if (payload.ignoreCache) {
      tab.view.webContents.reloadIgnoringCache();
    } else {
      tab.view.webContents.reload();
    }
  } catch (error) {
    console.warn('Failed to reload tab', { tabId: tab.id, error });
    tab.isLoading = false;
  }
  emitNavState(tab);
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
    app.on('second-instance', () => {
      if (mainWindow) {
        if (mainWindow.isMinimized()) {
          mainWindow.restore();
        }
        mainWindow.focus();
      }
    });

    app.whenReady().then(async () => {
      const mainSession = session.fromPartition(MAIN_SESSION_KEY);

      mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
        const headers = { ...details.requestHeaders };
        headers['User-Agent'] = DESKTOP_USER_AGENT;
        callback({ requestHeaders: headers });
      });

      mainSession.webRequest.onHeadersReceived((details, callback) => {
        const headers = details.responseHeaders || {};
        if (!app.isPackaged) {
          headers['Content-Security-Policy'] = [
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http: https:",
          ];
        }
        callback({ responseHeaders: headers });
      });

      const initialPromise = ensureInitialDiagnostics();
      buildApplicationMenu();
      mainWindow = createWindow();
      browserContentBounds = sanitizeBounds(browserContentBounds);
      if (!tabs.size) {
        await createBrowserTab(DEFAULT_TAB_URL, { activate: true });
      }

      initialPromise
        .then((report) => {
          if (report) {
            notifyRenderer('system-check:initial-report', report);
          } else if (process.env.SKIP_SYSTEM_CHECK === '1') {
            notifyRenderer('system-check:skipped');
          }
        })
        .catch((error) => {
          notifyRenderer('system-check:initial-error', error?.message || String(error));
        });

      app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
          mainWindow = createWindow();
          browserContentBounds = sanitizeBounds(browserContentBounds);
          void createBrowserTab(DEFAULT_TAB_URL, { activate: true });
        }
      });
    });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Electronmon handles live-reload during development by restarting the process.
