const { app, BrowserWindow, shell, Menu, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

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
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function safeJson(response) {
  return response
    .json()
    .catch(() => null);
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
      const initialPromise = ensureInitialDiagnostics();
      buildApplicationMenu();
      mainWindow = createWindow();

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
