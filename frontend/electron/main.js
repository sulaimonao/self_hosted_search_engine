import { app, BrowserWindow, ipcMain, session, webContents } from 'electron';
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

function loadAppUrl(win) {
  const target = resolveAppUrl();
  win.loadURL(target);
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

function createBrowserWindow() {
  sanitizeSandboxHeaders();

  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    title: 'Personal Search Engine',
    webPreferences: { ...sharedWebPreferences },
  });

  loadAppUrl(window);

  shadowModeByWindow.set(window.id, false);
  window.on('closed', () => {
    shadowModeByWindow.delete(window.id);
  });

  window.webContents.on('did-fail-load', (_event, _code, _desc, _url, isMainFrame) => {
    if (isMainFrame) {
      setTimeout(() => loadAppUrl(window), 800);
    }
  });

  window.webContents.on('did-navigate', (_event, url) => {
    window.webContents.send('nav-progress', { stage: 'navigated', url, tabId: window.id });
    postShadowCrawl(window, url, 'did-navigate');
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    const child = new BrowserWindow({
      parent: window,
      width: 1200,
      height: 800,
      webPreferences: { ...sharedWebPreferences },
    });
    child.webContents.on('did-navigate', (_event, targetUrl) => {
      child.webContents.send('nav-progress', { stage: 'navigated', url: targetUrl, tabId: child.id });
      postShadowCrawl(child, targetUrl, 'new-window');
    });
    child.loadURL(url);
    postShadowCrawl(child, url, 'new-window');
    shadowModeByWindow.set(child.id, isShadowModeEnabled(window));
    child.on('closed', () => {
      shadowModeByWindow.delete(child.id);
    });
    return { action: 'deny' };
  });

  session.defaultSession.webRequest.onCompleted((details) => {
    if (details.resourceType !== 'mainFrame') {
      return;
    }
    let recipient = window;
    if (typeof details.webContentsId === 'number' && typeof webContents.fromId === 'function') {
      try {
        const contents = webContents.fromId(details.webContentsId);
        if (contents) {
          const owningWindow = BrowserWindow.fromWebContents(contents);
          if (owningWindow) {
            recipient = owningWindow;
          }
        }
      } catch (error) {
        console.warn('nav-progress resolution failed', error);
      }
    }
    recipient.webContents.send('nav-progress', {
      stage: 'loaded',
      url: details.url,
      status: details.statusCode,
      tabId: recipient.id,
    });
  });

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
