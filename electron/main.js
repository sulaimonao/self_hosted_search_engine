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
const { initializeBrowserData } = require('./browser-data');

const DEFAULT_FRONTEND_ORIGIN = (() => {
  const fallbackHost = 'localhost';
  const fallbackPort = '3100';
  const host =
    typeof process.env.FRONTEND_HOST === 'string' && process.env.FRONTEND_HOST.trim().length > 0
      ? process.env.FRONTEND_HOST.trim()
      : fallbackHost;
  const rawPort = process.env.FRONTEND_PORT;
  const parsedPort = rawPort ? Number.parseInt(rawPort, 10) : NaN;
  const port = Number.isFinite(parsedPort) && parsedPort > 0 ? String(parsedPort) : fallbackPort;
  const protocol = process.env.FRONTEND_PROTOCOL?.trim().toLowerCase() === 'https' ? 'https' : 'http';
  return `${protocol}://${host}:${port}`;
})();
const FRONTEND_URL = process.env.FRONTEND_URL || DEFAULT_FRONTEND_ORIGIN;
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
app.commandLine.appendSwitch(
  'enable-features',
  'NetworkService,NetworkServiceInProcess,UserAgentClientHint,AcceptCHFrame,GreaseUACH',
);

const MAIN_SESSION_KEY = 'persist:main';
const DEFAULT_TAB_URL = 'https://wikipedia.org';
const DEFAULT_TAB_TITLE = 'New Tab';
const DEFAULT_BOUNDS = { x: 0, y: 136, width: 1280, height: 720 };
const NAV_STATE_CHANNEL = 'nav:state';
const TAB_LIST_CHANNEL = 'browser:tabs';
const HISTORY_CHANNEL = 'history:append';
const DOWNLOAD_CHANNEL = 'downloads:update';
const PERMISSION_PROMPT_CHANNEL = 'permissions:prompt';
const PERMISSION_STATE_CHANNEL = 'permissions:state';
const SETTINGS_CHANNEL = 'settings:state';
const CONTROLLED_PERMISSIONS = new Set(['camera', 'microphone', 'geolocation', 'notifications', 'clipboard-read']);

const tabs = new Map();
const tabOrder = [];
let activeTabId = null;
let browserContentBounds = { ...DEFAULT_BOUNDS };
let browserDataStore = null;
const pendingPermissionRequests = new Map();
let runtimeSettings = null;
const runtimeNetworkState = {
  userAgent: null,
  acceptLanguage: null,
  localeCountryCode: null,
  locale: null,
};

const DEFAULT_SETTINGS = {
  thirdPartyCookies: true,
  searchMode: 'auto',
  spellcheckLanguage: 'en-US',
  proxy: { mode: 'system', host: '', port: '' },
};

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

function getMainSession() {
  return session.fromPartition(MAIN_SESSION_KEY);
}

function normalizeSettings(candidate) {
  const base = { ...DEFAULT_SETTINGS };
  if (candidate && typeof candidate === 'object') {
    if (typeof candidate.thirdPartyCookies === 'boolean') {
      base.thirdPartyCookies = candidate.thirdPartyCookies;
    }
    if (candidate.searchMode === 'auto' || candidate.searchMode === 'query') {
      base.searchMode = candidate.searchMode;
    }
    if (typeof candidate.spellcheckLanguage === 'string' && candidate.spellcheckLanguage.trim()) {
      base.spellcheckLanguage = candidate.spellcheckLanguage.trim();
    }
    if (candidate.proxy && typeof candidate.proxy === 'object') {
      const proxy = {
        mode: candidate.proxy.mode === 'manual' ? 'manual' : 'system',
        host: typeof candidate.proxy.host === 'string' ? candidate.proxy.host : '',
        port: Number.isFinite(Number(candidate.proxy.port)) ? String(candidate.proxy.port) : '',
      };
      base.proxy = proxy;
    }
  }
  return base;
}

function emitSettingsState() {
  if (runtimeSettings) {
    sendToRenderer(SETTINGS_CHANNEL, runtimeSettings);
  }
}

function persistRuntimeSettings() {
  if (browserDataStore && runtimeSettings) {
    browserDataStore.setSetting('browser.settings', runtimeSettings);
  }
}

async function applyProxySettings(sess, proxySettings) {
  if (!sess || !proxySettings) {
    return;
  }
  if (proxySettings.mode === 'manual') {
    const host = (proxySettings.host || '').trim();
    const portValue = Number(proxySettings.port);
    if (host && Number.isFinite(portValue) && portValue > 0) {
      const proxyRules = `${host}:${portValue}`;
      try {
        await sess.setProxy({ proxyRules });
      } catch (error) {
        console.warn('Failed to apply manual proxy settings', { error });
      }
      return;
    }
  }
  try {
    await sess.setProxy({ mode: 'system' });
  } catch (error) {
    console.warn('Failed to reset proxy settings', { error });
  }
}

function applySpellcheckSettings(sess, language) {
  if (!sess || !language) {
    return;
  }
  try {
    sess.setSpellCheckerLanguages([language]);
  } catch (error) {
    console.warn('Failed to apply spellcheck language', { error });
  }
}

async function applyRuntimeSettingsToSession() {
  const sess = getMainSession();
  if (!sess || !runtimeSettings) {
    return;
  }
  applySpellcheckSettings(sess, runtimeSettings.spellcheckLanguage);
  await applyProxySettings(sess, runtimeSettings.proxy);
}

function loadRuntimeSettings() {
  const stored = browserDataStore?.getSetting('browser.settings');
  runtimeSettings = normalizeSettings(stored || null);
  persistRuntimeSettings();
  void applyRuntimeSettingsToSession();
  emitSettingsState();
}

function mergeSettings(base, patch) {
  const next = { ...base };
  if (!patch || typeof patch !== 'object') {
    return next;
  }
  for (const [key, value] of Object.entries(patch)) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      next[key] = mergeSettings(base[key] ?? {}, value);
    } else if (value !== undefined) {
      next[key] = value;
    }
  }
  return next;
}

function updateRuntimeSettings(patch) {
  const merged = mergeSettings(runtimeSettings ?? DEFAULT_SETTINGS, patch);
  runtimeSettings = normalizeSettings(merged);
  persistRuntimeSettings();
  void applyRuntimeSettingsToSession();
  emitSettingsState();
}

function canonicalizePermission(permission, details) {
  if (permission === 'media') {
    if (details?.mediaTypes?.includes('video')) {
      return 'camera';
    }
    if (details?.mediaTypes?.includes('audio')) {
      return 'microphone';
    }
  }
  return permission;
}

function resolveOrigin(candidate) {
  if (!candidate || typeof candidate !== 'string') {
    return null;
  }
  try {
    const url = new URL(candidate);
    return url.origin;
  } catch (error) {
    return null;
  }
}

function emitPermissionState(origin) {
  if (!browserDataStore || !origin) {
    return;
  }
  const entries = browserDataStore.listPermissions(origin);
  sendToRenderer(PERMISSION_STATE_CHANNEL, { origin, permissions: entries });
}

function registerPermissionHandlers(sess) {
  if (!sess) {
    return;
  }

  sess.setPermissionCheckHandler((_wc, permission, requestingOrigin, details) => {
    if (!runtimeSettings) {
      return undefined;
    }
    if (permission === 'cookies') {
      if (runtimeSettings.thirdPartyCookies) {
        return true;
      }
      const embeddingOrigin = details?.embeddingOrigin || requestingOrigin;
      if (!embeddingOrigin || embeddingOrigin === requestingOrigin) {
        return true;
      }
      return false;
    }
    return undefined;
  });

  sess.setPermissionRequestHandler((wc, permission, callback, details) => {
    const canonical = canonicalizePermission(permission, details);
    if (!CONTROLLED_PERMISSIONS.has(canonical)) {
      callback(true);
      return;
    }

    const requestingOrigin = resolveOrigin(details?.requestingUrl) || resolveOrigin(details?.securityOrigin);
    const origin = requestingOrigin || resolveOrigin(wc?.getURL());
    if (!origin) {
      callback(false);
      return;
    }

    const storedDecision = browserDataStore?.getPermission(origin, canonical);
    if (storedDecision === 'allow') {
      callback(true);
      return;
    }
    if (storedDecision === 'deny') {
      callback(false);
      return;
    }

    const requestId = randomUUID();
    const timeout = setTimeout(() => {
      const pending = pendingPermissionRequests.get(requestId);
      if (pending) {
        pendingPermissionRequests.delete(requestId);
        callback(false);
      }
    }, 30000);

    pendingPermissionRequests.set(requestId, {
      origin,
      permission: canonical,
      callback,
      timeout,
    });
    sendToRenderer(PERMISSION_PROMPT_CHANNEL, {
      id: requestId,
      origin,
      permission: canonical,
    });
  });
}

function settlePermissionRequest(requestId, decision, remember) {
  const pending = pendingPermissionRequests.get(requestId);
  if (!pending) {
    return;
  }
  pendingPermissionRequests.delete(requestId);
  clearTimeout(pending.timeout);

  const allow = decision === 'allow';
  try {
    pending.callback(allow);
  } catch (error) {
    console.warn('Permission callback failed', { error });
  }

  if (remember && browserDataStore) {
    browserDataStore.savePermission(pending.origin, pending.permission, allow ? 'allow' : 'deny');
    emitPermissionState(pending.origin);
  }
}

function clearStoredPermission(origin, permission) {
  if (!browserDataStore || !origin || !permission) {
    return;
  }
  browserDataStore.clearPermission(origin, permission);
  emitPermissionState(origin);
}

function clearAllPermissionsForOrigin(origin) {
  if (!browserDataStore || !origin) {
    return;
  }
  browserDataStore.clearPermissionsForOrigin(origin);
  emitPermissionState(origin);
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

function emitHistory(entry) {
  sendToRenderer(HISTORY_CHANNEL, entry);
}

function emitDownload(entry) {
  sendToRenderer(DOWNLOAD_CHANNEL, entry);
}

function recordNavigationEntry(tab, url, transition) {
  if (!browserDataStore) {
    return;
  }
  const entry = browserDataStore.recordNavigation({
    url,
    title: tab.title,
    transition,
    referrer: tab.lastReferrer,
  });
  tab.lastHistoryId = entry.id;
  tab.pendingReferrer = null;
  emitHistory({ ...entry, tabId: tab.id });
}

function updateHistoryTitle(tab) {
  if (browserDataStore && tab.lastHistoryId) {
    browserDataStore.updateHistoryTitle(tab.lastHistoryId, tab.title);
  }
}

function emitDownloadById(downloadId) {
  if (!browserDataStore) {
    return;
  }
  const entry = browserDataStore.getDownload(downloadId);
  if (entry) {
    emitDownload(entry);
  }
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

  wc.on('did-start-navigation', (_event, url, isInPlace, isMainFrame) => {
    if (!isMainFrame) return;
    tab.isLoading = true;
    tab.lastError = null;
    const previousUrl = tab.lastUrl;
    tab.lastReferrer = tab.pendingReferrer ?? (previousUrl && previousUrl !== url ? previousUrl : null);
    tab.pendingReferrer = null;
    if (isInPlace) {
      tab.pendingTransition = 'in_page';
    }
    tab.lastUrl = url;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-navigate', (_event, url) => {
    tab.lastUrl = url;
    tab.isLoading = false;
    tab.lastError = null;
    const transition = tab.pendingTransition && tab.pendingTransition !== 'auto' ? tab.pendingTransition : 'link';
    recordNavigationEntry(tab, url, transition);
    tab.pendingTransition = 'auto';
    tab.lastReferrer = url;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-navigate-in-page', (_event, url, isMainFrame) => {
    if (!isMainFrame) {
      return;
    }
    tab.lastUrl = url;
    recordNavigationEntry(tab, url, 'in_page');
    tab.lastReferrer = url;
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
    updateHistoryTitle(tab);
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
    tab.pendingTransition = 'auto';
    tab.pendingReferrer = null;
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

  const tab = {
    id,
    view,
    title: DEFAULT_TAB_TITLE,
    favicon: null,
    lastUrl: DEFAULT_TAB_URL,
    isLoading: false,
    lastError: null,
    lastHistoryId: null,
    lastReferrer: null,
    pendingTransition: typeof options.transition === 'string' ? options.transition : 'typed',
    pendingReferrer: null,
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

ipcMain.handle('history:list', async (_event, payload = {}) => {
  if (!browserDataStore) {
    return [];
  }
  const limit = Number.isFinite(Number(payload.limit)) ? Math.max(1, Math.min(Number(payload.limit), 500)) : 100;
  return browserDataStore.getRecentHistory(limit).map((entry) => ({ ...entry }));
});

ipcMain.handle('downloads:list', async (_event, payload = {}) => {
  if (!browserDataStore) {
    return [];
  }
  const limit = Number.isFinite(Number(payload.limit)) ? Math.max(1, Math.min(Number(payload.limit), 200)) : 50;
  return browserDataStore.listDownloads(limit);
});

ipcMain.handle('downloads:show-in-folder', async (_event, payload = {}) => {
  const id = typeof payload.id === 'string' ? payload.id : '';
  if (!browserDataStore || !id) {
    return { ok: false };
  }
  const entry = browserDataStore.getDownload(id);
  if (!entry || !entry.path) {
    return { ok: false, missing: true };
  }
  try {
    shell.showItemInFolder(entry.path);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }
});

ipcMain.handle('settings:get', async () => runtimeSettings ?? DEFAULT_SETTINGS);

ipcMain.handle('settings:update', async (_event, patch = {}) => {
  updateRuntimeSettings(patch);
  return runtimeSettings;
});

ipcMain.handle('permissions:list', async (_event, payload = {}) => {
  if (!browserDataStore) {
    return [];
  }
  const origin = typeof payload.origin === 'string' ? payload.origin : '';
  if (!origin) {
    return [];
  }
  return browserDataStore.listPermissions(origin);
});

ipcMain.on('permissions:decision', (_event, payload = {}) => {
  const id = typeof payload.id === 'string' ? payload.id : '';
  if (!id) {
    return;
  }
  const decision = payload.decision === 'allow' ? 'allow' : 'deny';
  const remember = payload.remember !== false;
  settlePermissionRequest(id, decision, remember);
});

ipcMain.handle('permissions:clear', async (_event, payload = {}) => {
  const origin = typeof payload.origin === 'string' ? payload.origin : '';
  const permission = typeof payload.permission === 'string' ? payload.permission : '';
  clearStoredPermission(origin, permission);
  return { ok: true };
});

ipcMain.handle('permissions:clear-origin', async (_event, payload = {}) => {
  const origin = typeof payload.origin === 'string' ? payload.origin : '';
  clearAllPermissionsForOrigin(origin);
  return { ok: true };
});

ipcMain.handle('permissions:set', async (_event, payload = {}) => {
  const origin = typeof payload.origin === 'string' ? payload.origin : '';
  const permission = typeof payload.permission === 'string' ? payload.permission : '';
  const setting = payload.setting === 'allow' ? 'allow' : payload.setting === 'deny' ? 'deny' : null;
  if (!browserDataStore || !origin || !permission || !setting) {
    return { ok: false };
  }
  browserDataStore.savePermission(origin, permission, setting);
  emitPermissionState(origin);
  return { ok: true };
});

ipcMain.handle('site:clear-data', async (_event, payload = {}) => {
  const origin = typeof payload.origin === 'string' ? payload.origin : '';
  if (!origin) {
    return { ok: false };
  }
  try {
    const sess = getMainSession();
    if (!sess) {
      return { ok: false };
    }
    await sess.clearStorageData({ origin });
    return { ok: true };
  } catch (error) {
    console.warn('Failed to clear site data', { origin, error });
    return { ok: false, error: error?.message || String(error) };
  }
});

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
  tab.pendingTransition = typeof payload.transition === 'string' ? payload.transition : 'typed';
  tab.pendingReferrer = tab.lastUrl;
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
    tab.pendingTransition = 'back_forward';
    tab.pendingReferrer = tab.lastUrl;
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
    tab.pendingTransition = 'back_forward';
    tab.pendingReferrer = tab.lastUrl;
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
  tab.pendingTransition = 'reload';
  tab.pendingReferrer = tab.lastUrl;
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

      const defaultUA =
        (typeof mainSession.getUserAgent === 'function' && mainSession.getUserAgent()) ||
        app.userAgentFallback ||
        null;
      const localeCountryCode =
        typeof app.getLocaleCountryCode === 'function' ? app.getLocaleCountryCode() : null;
      const preferredLocale = typeof app.getLocale === 'function' ? app.getLocale() : null;

      runtimeNetworkState.userAgent = defaultUA;
      runtimeNetworkState.localeCountryCode = localeCountryCode;
      runtimeNetworkState.locale = preferredLocale;

      let acceptLanguage = null;
      if (preferredLocale && typeof preferredLocale === 'string') {
        const normalized = preferredLocale.trim();
        if (normalized) {
          const [language] = normalized.split('-');
          if (language && language.length && language.toLowerCase() !== normalized.toLowerCase()) {
            acceptLanguage = `${normalized},${language};q=0.9`;
          } else {
            acceptLanguage = normalized;
          }
        }
      }

      runtimeNetworkState.acceptLanguage = acceptLanguage;

      if (!browserDataStore) {
        browserDataStore = initializeBrowserData(app);
        loadRuntimeSettings();
      }

      registerPermissionHandlers(mainSession);

      mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
        const headers = { ...details.requestHeaders };
        if (!headers['User-Agent'] && runtimeNetworkState.userAgent) {
          headers['User-Agent'] = runtimeNetworkState.userAgent;
        }
        if (!headers['Accept-Language'] && runtimeNetworkState.acceptLanguage) {
          headers['Accept-Language'] = runtimeNetworkState.acceptLanguage;
        }
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

      mainSession.on('will-download', (_event, item) => {
        if (!browserDataStore) {
          return;
        }
        const downloadId = randomUUID();
        const filename = item.getFilename();
        const savePath = path.join(app.getPath('downloads'), filename);
        try {
          item.setSavePath(savePath);
        } catch (error) {
          console.warn('Failed to set download save path', { error });
        }
        const initialEntry = {
          id: downloadId,
          url: item.getURL(),
          filename,
          mime: item.getMimeType(),
          bytesTotal: item.getTotalBytes() > 0 ? item.getTotalBytes() : null,
          bytesReceived: item.getReceivedBytes(),
          path: savePath,
          state: 'in_progress',
          startedAt: Date.now(),
          completedAt: null,
        };
        browserDataStore.recordDownload(initialEntry);
        emitDownload(initialEntry);

        item.on('updated', (_updateEvent, state) => {
          browserDataStore.updateDownloadProgress(downloadId, {
            bytesReceived: item.getReceivedBytes(),
            bytesTotal: item.getTotalBytes() > 0 ? item.getTotalBytes() : null,
            state: state === 'interrupted' ? 'interrupted' : 'in_progress',
            path: savePath,
          });
          emitDownloadById(downloadId);
        });

        item.once('done', (_doneEvent, state) => {
          const finalState = state === 'completed' ? 'completed' : state === 'cancelled' ? 'cancelled' : 'interrupted';
          browserDataStore.updateDownloadProgress(downloadId, {
            bytesReceived: item.getReceivedBytes(),
            bytesTotal: item.getTotalBytes() > 0 ? item.getTotalBytes() : null,
            state: finalState,
            path: savePath,
            completedAt: Date.now(),
          });
          emitDownloadById(downloadId);
        });
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
