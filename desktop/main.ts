import { app, BrowserWindow, session, ipcMain, Menu, shell } from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import log from 'electron-log';

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

const require = createRequire(import.meta.url);
const { runBrowserDiagnostics }: {
  runBrowserDiagnostics: (options?: {
    timeoutMs?: number;
    write?: boolean;
    log?: boolean;
  }) => Promise<BrowserDiagnosticsReport>;
} = require('../scripts/diagnoseBrowser.js');

const DEFAULT_FRONTEND_URL = 'http://localhost:3100';
const DEFAULT_API_URL = 'http://127.0.0.1:5050';
const FRONTEND_URL = process.env.APP_URL || process.env.FRONTEND_URL || DEFAULT_FRONTEND_URL;
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

const isDev = !app.isPackaged;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

let win: BrowserWindow | null = null;
let lastSystemCheck: SystemCheckResult = null;
let initialSystemCheckPromise: Promise<SystemCheckResult> | null = null;

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
  if (win && !win.isDestroyed()) {
    win.webContents.send(channel, payload);
  }
}

async function safeJson<T = unknown>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
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
    width: 1300,
    height: 900,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.once('ready-to-show', () => win?.show());

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  const target = resolveFrontendTarget();
  win
    .loadURL(target)
    .catch((error) => {
      log.error('Failed to load frontend', error);
    });

  win.on('closed', () => {
    win = null;
  });
}

app.whenReady().then(async () => {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
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
