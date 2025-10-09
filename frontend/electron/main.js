import { app, BrowserWindow, session, webContents } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow;

function resolveAppUrl() {
  const isDev = process.env.NODE_ENV !== 'production';
  if (process.env.APP_URL) {
    return process.env.APP_URL;
  }
  return isDev
    ? 'http://localhost:3100'
    : `file://${path.join(__dirname, '../out/index.html')}`;
}

function loadAppUrl(win) {
  const target = resolveAppUrl();
  win.loadURL(target);
}

function postShadowCrawl(win, targetUrl, reason) {
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
