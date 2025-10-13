import { app, BrowserWindow, BrowserView, ipcMain, session, webContents } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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

function isShadowModeEnabled(win) {
  if (!win) {
    return false;
  }
  return Boolean(shadowModeByWindow.get(win.id));
}

function resolveAppUrl() {
  const defaultUrl = 'http://localhost:3100';
  const envUrl = [process.env.APP_URL, process.env.ELECTRON_START_URL].find(
    (value) => typeof value === 'string' && value.trim().length > 0,
  );
  return envUrl ?? defaultUrl;
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
    console.warn('shadow crawl request failed', error);
  }
}

function attachView(window, view) {
  window.setBrowserView(view);
  view.setAutoResize({ width: true, height: true });
  const updateBounds = () => {
    const [width, height] = window.getContentSize();
    view.setBounds({ x: 0, y: 0, width, height });
  };
  updateBounds();
  window.on('resize', updateBounds);
  window.on('enter-full-screen', updateBounds);
  window.on('leave-full-screen', updateBounds);
  return () => {
    window.removeListener('resize', updateBounds);
    window.removeListener('enter-full-screen', updateBounds);
    window.removeListener('leave-full-screen', updateBounds);
  };
}

function attachNavigationHandlers(window, view, initialUrl) {
  const fallbackUrl = typeof initialUrl === 'string' && initialUrl.trim().length > 0 ? initialUrl : resolveAppUrl();

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
    }, 800);
  });

  view.webContents.on('did-navigate', (_event, url) => {
    if (view.webContents.isDestroyed()) {
      return;
    }
    view.webContents.send('nav-progress', { stage: 'navigated', url, tabId: window.id });
    postShadowCrawl(window, url, 'did-navigate');
  });

  view.webContents.setWindowOpenHandler(({ url }) => {
    const child = createBrowserWindow({
      parent: window,
      initialUrl: url,
      shadowEnabled: isShadowModeEnabled(window),
    });
    postShadowCrawl(child, url, 'new-window');
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
        console.warn('nav-progress resolution failed', error);
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
      console.warn('nav-progress delivery failed', error);
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
    show: true,
    backgroundColor: '#0b0d17',
  });

  const view = new BrowserView({ webPreferences: { ...sharedWebPreferences } });
  const detachView = attachView(window, view);

  const targetUrl = typeof initialUrl === 'string' && initialUrl.trim().length > 0 ? initialUrl : resolveAppUrl();
  view.webContents.loadURL(targetUrl).catch((error) => {
    console.warn('initial load failed', error);
  });

  shadowModeByWindow.set(window.id, Boolean(shadowEnabled));

  window.on('closed', () => {
    detachView();
    shadowModeByWindow.delete(window.id);
  });

  attachNavigationHandlers(window, view, targetUrl);

  return window;
}

function createWindow() {
  mainWindow = createBrowserWindow();
}

app.whenReady().then(() => {
  ipcMain.on('shadow-mode:update', (event, payload) => {
    const sender = event?.sender;
    const win = sender ? BrowserWindow.fromWebContents(sender) : null;
    if (!win) {
      return;
    }
    shadowModeByWindow.set(win.id, Boolean(payload?.enabled));
  });

  createWindow();
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
