import { app, BrowserWindow, BrowserView, ipcMain, session, shell, webContents } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import waitOn from 'wait-on';
import logger from '../../shared/logger/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DEV_BROWSER_PATH = '/browser';
const FRONTEND_WAIT_TIMEOUT_MS = Number(process.env.ELECTRON_WAIT_TIMEOUT_MS ?? '60000');

const DEFAULT_DEV_SERVER_ORIGIN = (() => {
  const fallbackHost = 'localhost';
  const fallbackPort = '3100';
  const host = typeof process.env.DEV_SERVER_HOST === 'string' && process.env.DEV_SERVER_HOST.trim().length > 0
    ? process.env.DEV_SERVER_HOST.trim()
    : fallbackHost;
  const portCandidate = process.env.DEV_SERVER_PORT ?? fallbackPort;
  const parsedPort = Number.parseInt(portCandidate, 10);
  const port = Number.isFinite(parsedPort) && parsedPort > 0 ? String(parsedPort) : fallbackPort;
  const protocol = process.env.DEV_SERVER_PROTOCOL?.trim().toLowerCase() === 'https' ? 'https' : 'http';
  return `${protocol}://${host}:${port}`;
})();

const sharedWebPreferences = Object.freeze({
  preload: path.join(__dirname, 'preload.js'),
  contextIsolation: true,
  sandbox: false,
  nodeIntegration: false,
  webviewTag: true,
  enableRemoteModule: false,
});

let mainWindow;
const shadowModeByWindow = new Map();
let frameBypassHookRegistered = false;
const log = logger.child({ component: 'electron-main', pid: process.pid });

if (!globalThis.__frontendElectronLoggerHandlersRegistered) {
  process.on('uncaughtException', (error) => {
    log.error('Uncaught exception in Electron main process', {
      message: error?.message,
      stack: error?.stack,
    });
  });
  process.on('unhandledRejection', (reason) => {
    if (reason instanceof Error) {
      log.error('Unhandled promise rejection in Electron main process', {
        message: reason.message,
        stack: reason.stack,
      });
      return;
    }
    let serialized;
    try {
      serialized = typeof reason === 'object' ? JSON.stringify(reason) : String(reason);
    } catch {
      serialized = String(reason);
    }
    log.error('Unhandled promise rejection in Electron main process', { reason: serialized });
  });
  globalThis.__frontendElectronLoggerHandlersRegistered = true;
}

function isShadowModeEnabled(win) {
  if (!win) {
    return false;
  }
  return Boolean(shadowModeByWindow.get(win.id));
}

function resolveBaseUrl() {
  const packagedFallback = `file://${path.join(__dirname, 'index.html')}`;
  const defaultUrl = app.isPackaged ? packagedFallback : DEFAULT_DEV_SERVER_ORIGIN;
  const envUrl = [process.env.RENDERER_URL, process.env.APP_URL, process.env.ELECTRON_START_URL].find(
    (value) => typeof value === 'string' && value.trim().length > 0,
  );
  return envUrl ?? defaultUrl;
}

function isHttpUrl(candidate) {
  if (typeof candidate !== 'string') {
    return false;
  }
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function resolveBrowserStartUrl() {
  const base = resolveBaseUrl();
  if (!isHttpUrl(base)) {
    return base;
  }
  try {
    const parsed = new URL(base);
    parsed.pathname = DEV_BROWSER_PATH;
    parsed.hash = '';
    return parsed.toString();
  } catch {
    const sanitized = base.endsWith('/') ? base.slice(0, -1) : base;
    return `${sanitized}${DEV_BROWSER_PATH}`;
  }
}

function resolveAppOrigin(url = resolveBrowserStartUrl()) {
  if (!isHttpUrl(url)) {
    return null;
  }
  try {
    const parsed = new URL(url);
    return parsed.origin;
  } catch {
    return null;
  }
}

async function waitForRenderer(url) {
  if (app.isPackaged) {
    return;
  }
  if (!isHttpUrl(url)) {
    return;
  }
  await waitOn({
    resources: [url],
    timeout: FRONTEND_WAIT_TIMEOUT_MS,
    validateStatus: (status) => status === 200,
  });
}

function sanitizeSandboxHeaders() {
  if (frameBypassHookRegistered) {
    return;
  }
  frameBypassHookRegistered = true;
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    try {
      const url = new URL(details.url);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        callback({ cancel: false, responseHeaders: details.responseHeaders });
        return;
      }
    } catch {
      callback({ cancel: false, responseHeaders: details.responseHeaders });
      return;
    }

    const { responseHeaders } = details;
    if (!responseHeaders) {
      callback({ cancel: false, responseHeaders });
      return;
    }

    const lowerCaseMap = new Map(
      Object.keys(responseHeaders).map((key) => [key.toLowerCase(), key]),
    );

    const clonedHeaders = { ...responseHeaders };

    const frameOptionsKey = lowerCaseMap.get('x-frame-options');
    if (frameOptionsKey) {
      delete clonedHeaders[frameOptionsKey];
    }

    const cspKey = lowerCaseMap.get('content-security-policy');
    if (cspKey) {
      const original = responseHeaders[cspKey];
      if (Array.isArray(original)) {
        const updated = original
          .map((value) => {
            if (typeof value !== 'string') {
              return value;
            }
            const segments = value
              .split(';')
              .map((segment) => segment.trim())
              .filter((segment) => segment.length > 0);
            const filtered = segments.filter(
              (segment) => !segment.toLowerCase().startsWith('frame-ancestors'),
            );
            return filtered.join('; ');
          })
          .filter((entry) => typeof entry === 'string' && entry.length > 0);
        if (updated.length > 0) {
          clonedHeaders[cspKey] = updated;
        } else {
          delete clonedHeaders[cspKey];
        }
      } else {
        delete clonedHeaders[cspKey];
      }
    }

    callback({ cancel: false, responseHeaders: clonedHeaders });
  });
}

function postShadowCrawl(win, targetUrl, reason) {
  if (!isShadowModeEnabled(win)) {
    return;
  }
  if (!targetUrl || typeof targetUrl !== 'string') {
    return;
  }
  const payload = {
    url: targetUrl,
    reason,
    tabId: win?.id,
  };
  try {
    fetch('http://127.0.0.1:5050/api/shadow/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {
      // Non-fatal during development when backend may be offline.
    });
  } catch (error) {
    // Intentionally ignore network errors; renderer will surface failures if needed.
    log.warn('Shadow crawl request failed', {
      message: error?.message,
      stack: error?.stack,
    });
  }
}

function attachView(window, view) {
  window.setBrowserView(view);
  view.setAutoResize({ width: true, height: true });
  const updateBounds = () => {
    if (window.isDestroyed()) {
      return;
    }
    const [width, height] = window.getContentSize();
    try {
      view.setBounds({ x: 0, y: 0, width, height });
    } catch (error) {
      log.warn('Failed to resize BrowserView', {
        message: error?.message,
        stack: error?.stack,
      });
    }
  };
  const resizeEvents = [
    'resize',
    'resized',
    'will-resize',
    'enter-full-screen',
    'leave-full-screen',
    'maximize',
    'unmaximize',
    'restore',
  ];
  updateBounds();
  for (const eventName of resizeEvents) {
    window.on(eventName, updateBounds);
  }
  return () => {
    for (const eventName of resizeEvents) {
      window.removeListener(eventName, updateBounds);
    }
    if (!window.isDestroyed()) {
      window.setBrowserView(null);
    }
  };
}

function attachNavigationHandlers(window, view, initialUrl) {
  const fallbackUrl =
    typeof initialUrl === 'string' && initialUrl.trim().length > 0 ? initialUrl : resolveBrowserStartUrl();
  const appOrigin = resolveAppOrigin(fallbackUrl);

  view.webContents.on('did-fail-load', (_event, _code, _desc, failingUrl, isMainFrame) => {
    if (!isMainFrame) {
      return;
    }
    const retry = typeof failingUrl === 'string' && failingUrl.trim().length > 0 ? failingUrl : fallbackUrl;
  setTimeout(() => {
      if (!view.webContents.isDestroyed()) {
        view.webContents.loadURL(retry).catch(() => {
          // Ignore reload failures, the banner in renderer will surface state.
        });
      }
  }, 3000);
  });

  view.webContents.on('did-navigate', (_event, url) => {
    if (view.webContents.isDestroyed()) {
      return;
    }
    view.webContents.send('nav-progress', { stage: 'navigated', url, tabId: window.id });
    postShadowCrawl(window, url, 'did-navigate');
  });

  view.webContents.setWindowOpenHandler(({ url }) => {
    if (appOrigin && isHttpUrl(url)) {
      try {
        const parsed = new URL(url);
        if (parsed.origin === appOrigin) {
          view.webContents.loadURL(url).catch(() => {});
          postShadowCrawl(window, url, 'new-window');
          return { action: 'deny' };
        }
      } catch {
        // fall through to external handler
      }
    }
    shell.openExternal(url).catch(() => {});
    return { action: 'deny' };
  });

  session.defaultSession.webRequest.onCompleted((details) => {
    if (details.resourceType !== 'mainFrame') {
      return;
    }
    let recipient = view.webContents;
    let tabId = window.id;
    if (typeof details.webContentsId === 'number' && typeof webContents.fromId === 'function') {
      try {
        const contents = webContents.fromId(details.webContentsId);
        if (contents) {
          recipient = contents;
          const owningWindow = BrowserWindow.fromWebContents(contents);
          if (owningWindow) {
            tabId = owningWindow.id;
          }
        }
      } catch (error) {
        log.warn('nav-progress resolution failed', {
          message: error?.message,
          stack: error?.stack,
        });
      }
    }
    try {
      recipient.send('nav-progress', {
        stage: 'loaded',
        url: details.url,
        status: details.statusCode,
        tabId,
      });
    } catch (error) {
      log.warn('nav-progress delivery failed', {
        message: error?.message,
        stack: error?.stack,
      });
    }
  });
}

function createBrowserWindow({ parent = null, initialUrl = null, shadowEnabled = false } = {}) {
  sanitizeSandboxHeaders();

  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    title: 'Personal Search Engine',
    parent: parent ?? undefined,
    show: false,
    backgroundColor: '#0b0d17',
  });

  const view = new BrowserView({ webPreferences: { ...sharedWebPreferences } });
  const detachView = attachView(window, view);

  const targetUrl =
    typeof initialUrl === 'string' && initialUrl.trim().length > 0 ? initialUrl : resolveBrowserStartUrl();
  log.info('Creating BrowserWindow', { targetUrl, shadowEnabled: Boolean(shadowEnabled) });

  const revealWindow = () => {
    if (!window.isDestroyed()) {
      window.show();
    }
  };

  window.once('ready-to-show', () => {
    log.info('BrowserWindow ready to show', { windowId: window.id });
    revealWindow();
  });
  view.webContents.once('did-finish-load', revealWindow);

  view.webContents.loadURL(targetUrl).catch((error) => {
    log.error('Initial BrowserView load failed', {
      message: error?.message,
      stack: error?.stack,
      targetUrl,
    });
  });

  shadowModeByWindow.set(window.id, Boolean(shadowEnabled));

  window.on('closed', () => {
    log.info('BrowserWindow closed', { windowId: window.id });
    detachView();
    shadowModeByWindow.delete(window.id);
  });

  attachNavigationHandlers(window, view, targetUrl);

  return window;
}

async function createWindow(options = {}) {
  const requestedUrl = typeof options.initialUrl === 'string' ? options.initialUrl : null;
  const targetUrl = requestedUrl && requestedUrl.trim().length > 0 ? requestedUrl : resolveBrowserStartUrl();
  await waitForRenderer(targetUrl);
  log.info('Launching main BrowserWindow', { targetUrl });
  mainWindow = createBrowserWindow({
    ...options,
    initialUrl: targetUrl,
  });
  return mainWindow;
}

app.whenReady().then(async () => {
  log.info('Electron runtime ready (frontend shell)');
  ipcMain.on('shadow-mode:update', (event, payload) => {
    const sender = event?.sender;
    const win = sender ? BrowserWindow.fromWebContents(sender) : null;
    if (!win) {
      return;
    }
    shadowModeByWindow.set(win.id, Boolean(payload?.enabled));
  });

  await createWindow();
  app.on('activate', () => {
    log.info('Electron app activate event received');
    if (BrowserWindow.getAllWindows().length === 0) {
      void createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  log.info('All BrowserWindows closed (frontend shell)');
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
