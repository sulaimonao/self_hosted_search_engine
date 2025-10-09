import { app, BrowserWindow, session, ipcMain, Menu } from 'electron';
import path from 'node:path';
import log from 'electron-log';

const isDev = !app.isPackaged;
const FRONTEND_DEV_URL = process.env.APP_URL || 'http://localhost:3100';
const API_URL = process.env.API_URL || 'http://127.0.0.1:5050';

let win: BrowserWindow | null = null;

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

  if (isDev) {
    win.loadURL(FRONTEND_DEV_URL);
  } else {
    win.loadFile(path.join(process.resourcesPath, 'frontend', 'index.html'));
  }

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

  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'Researcher',
      submenu: [
        { label: 'Toggle Shadow Mode', click: () => win?.webContents.send('shadow/toggle') },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));

  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.handle('shadow:capture', async (_evt, payload) => {
  try {
    const res = await fetch(`${API_URL}/api/shadow/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  } catch (e: any) {
    log.error('shadow:capture failed', e);
    return { ok: false, error: String(e) };
  }
});

ipcMain.handle('index:search', async (_evt, q: string) => {
  try {
    const res = await fetch(`${API_URL}/api/index/search?q=${encodeURIComponent(q)}`);
    return { ok: res.ok, data: await res.json().catch(() => ({})) };
  } catch (e: any) {
    log.error('index:search failed', e);
    return { ok: false, error: String(e) };
  }
});
