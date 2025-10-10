import { app, BrowserWindow, ipcMain, session, webContents } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow;
const shadowModeByWindow = new Map();

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
  const window = new BrowserWindow({
    width: 1280,
    height: 820,
    title: 'Personal Search Engine',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
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
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
      },
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
