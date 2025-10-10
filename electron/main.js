const { app, BrowserWindow, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const DEFAULT_FRONTEND_URL = 'http://localhost:3100';
const FRONTEND_URL = process.env.FRONTEND_URL || DEFAULT_FRONTEND_URL;

let mainWindow;

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

function loadFrontend(win) {
  const target = resolveFrontendUrl();
  win.loadURL(target);
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 850,
    title: 'Personal Search Engine',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  loadFrontend(win);

  win.webContents.on('did-fail-load', (_event, _code, _desc, _url, isMainFrame) => {
    if (isMainFrame) {
      setTimeout(() => loadFrontend(win), 800);
    }
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  win.on('closed', () => {
    if (mainWindow === win) {
      mainWindow = null;
    }
  });

  return win;
}

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

  app.whenReady().then(() => {
    mainWindow = createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        mainWindow = createWindow();
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
