import {
  app,
  BrowserView,
  BrowserWindow,
  dialog,
  ipcMain,
  protocol,
  session,
  shell,
} from "electron";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawn, SpawnOptions } from "node:child_process";
import fs from "node:fs";
import fetch from "node-fetch";

let win: BrowserWindow | null = null;
let liveView: BrowserView | null = null;
let backendProc: ReturnType<typeof spawn> | null = null;
let isQuitting = false;
let appProtocolRegistered = false;

const MAIN_SESSION_KEY = "persist:main";
const DESKTOP_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";
const RESOLVED_USER_AGENT = (() => {
  const candidate = process.env.DESKTOP_USER_AGENT;
  if (typeof candidate === "string") {
    const trimmed = candidate.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
  }
  return DESKTOP_USER_AGENT;
})();

const FRONTEND_URL = process.env.FRONTEND_URL;
const IS_DEV = Boolean(FRONTEND_URL) || process.env.NODE_ENV === "development";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

function resolvePackagedFrontend(): string {
  const base = path.join(process.resourcesPath, "app-frontend");
  const htmlEntry = path.join(base, "index.html");
  if (fs.existsSync(htmlEntry)) {
    return "app://-/index.html";
  }
  if (fs.existsSync(base)) {
    return pathToFileURL(htmlEntry).toString();
  }
  throw new Error("Frontend assets not found. Ensure extraResources bundles app-frontend.");
}

async function waitForHealth(): Promise<boolean> {
  const url = "http://127.0.0.1:5050/api/llm/health";
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function startBackend(dataDir: string): Promise<void> {
  let cmd: string;
  let args: string[] = [];
  const env = { ...process.env };
  if (!env.DATA_DIR) {
    env.DATA_DIR = dataDir;
  }
  env.BACKEND_HOST = env.BACKEND_HOST ?? "127.0.0.1";
  env.BACKEND_PORT = env.BACKEND_PORT ?? "5050";

  const opts: SpawnOptions = {
    stdio: "inherit",
    env,
  };

  if (process.env.BACKEND_DEV === "1" || IS_DEV) {
    cmd = "python3.11";
    args = ["-m", "backend.app"];
    const repoRoot = path.resolve(__dirname, "../../..");
    opts.cwd = repoRoot;
    if (env.PYTHONPATH) {
      env.PYTHONPATH = `${repoRoot}${path.delimiter}${env.PYTHONPATH}`;
    } else {
      env.PYTHONPATH = repoRoot;
    }
  } else {
    const bin = path.join(process.resourcesPath, "backend-server");
    if (!fs.existsSync(bin)) {
      throw new Error("backend-server binary missing in resourcesPath");
    }
    cmd = bin;
    args = ["--port", "5050"];
    opts.cwd = process.resourcesPath;
  }

  backendProc = spawn(cmd, args, opts);
  backendProc.on("error", (error) => {
    console.error("Failed to start backend:", error);
  });
  backendProc.on("exit", (code, signal) => {
    backendProc = null;
    if (!isQuitting) {
      console.error(`Backend exited unexpectedly (code=${code}, signal=${signal ?? ""}).`);
      app.quit();
    }
  });

  const startTime = Date.now();
  while (true) {
    const healthy = await waitForHealth();
    if (healthy) {
      break;
    }
    if (backendProc === null) {
      throw new Error("Backend process exited before becoming healthy");
    }
    if (Date.now() - startTime > 20000) {
      throw new Error("Backend did not start within 20s");
    }
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
}

function registerAppProtocol() {
  if (appProtocolRegistered) {
    return;
  }
  protocol.registerFileProtocol("app", (request, callback) => {
    const base = path.join(process.resourcesPath, "app-frontend");
    const rawPath = request.url.replace("app://-", "");
    const normalized = path.normalize(rawPath).replace(/^([/\\])/, "");
    const target = path.resolve(base, normalized || "index.html");
    const relative = path.relative(base, target);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      callback({ error: -6 });
      return;
    }
    callback({ path: target });
  });
  appProtocolRegistered = true;
}

function attachLiveView(browserWindow: BrowserWindow) {
  liveView = new BrowserView({
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      partition: MAIN_SESSION_KEY ?? "persist:main",
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  browserWindow.setBrowserView(liveView);
  const padTop = 84;
  const resize = () => {
    if (!liveView || browserWindow.isDestroyed()) {
      return;
    }
    const [width, height] = browserWindow.getContentSize();
    liveView.setBounds({ x: 0, y: padTop, width, height: Math.max(0, height - padTop) });
  };
  browserWindow.on("resize", resize);
  browserWindow.on("enter-full-screen", resize);
  browserWindow.on("leave-full-screen", resize);
  resize();

  liveView.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });
  liveView.webContents.on("did-fail-load", (_event, _errorCode, _errorDescription, validatedURL, isMainFrame) => {
    if (isMainFrame) {
      browserWindow.webContents.send("viewer-fallback", { url: validatedURL });
    }
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 900,
    title: "Omni Desktop",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
      webviewTag: true,
      partition: MAIN_SESSION_KEY ?? "persist:main",
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  attachLiveView(win);

  if (IS_DEV && FRONTEND_URL) {
    win.loadURL(FRONTEND_URL).catch((error) => {
      console.error("Failed to load frontend:", error);
    });
  } else {
    registerAppProtocol();
    const target = resolvePackagedFrontend();
    win.loadURL(target).catch((error) => {
      console.error("Failed to load packaged frontend:", error);
    });
  }

  ipcMain.handle("open-url", async (_event, url: string) => {
    if (!liveView) {
      return;
    }
    try {
      await liveView.webContents.loadURL(url, {
        userAgent: RESOLVED_USER_AGENT,
      });
    } catch (error) {
      console.warn("Live view load failed", error);
      win?.webContents.send("viewer-fallback", { url });
    }
  });

  ipcMain.handle("pick-dir", async () => {
    if (!win) {
      return null;
    }
    const result = await dialog.showOpenDialog(win, {
      properties: ["openDirectory", "createDirectory"],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("quit", () => {
    app.quit();
  });

  win.on("closed", () => {
    win = null;
    liveView = null;
  });
}

app.whenReady().then(async () => {
  const mainSession = session.fromPartition(MAIN_SESSION_KEY);
  mainSession.setUserAgent(RESOLVED_USER_AGENT);
  mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const acceptLanguageHeader =
      details.requestHeaders["Accept-Language"] ??
      details.requestHeaders["accept-language"];

    const hintKeys = [
      "sec-ch-ua",
      "sec-ch-ua-mobile",
      "sec-ch-ua-platform",
      "sec-ch-ua-arch",
      "sec-ch-ua-model",
      "sec-ch-ua-platform-version",
      "sec-ch-ua-full-version-list",
    ];

    const headers = {
      ...details.requestHeaders,
      "User-Agent": RESOLVED_USER_AGENT,
    };

    if (acceptLanguageHeader) {
      headers["Accept-Language"] = acceptLanguageHeader;
    } else if (!headers["Accept-Language"]) {
      const locale = app.getLocale();
      if (locale) {
        headers["Accept-Language"] = locale;
      }
    }

    for (const key of hintKeys) {
      const value =
        details.requestHeaders[key] ?? details.requestHeaders[key.toUpperCase()];
      if (value != null) {
        headers[key] = value;
      }
    }

    headers["sec-ch-ua"] =
      headers["sec-ch-ua"] ?? '"Chromium";v="120", "Not A(Brand";v="99"';
    headers["sec-ch-ua-mobile"] = headers["sec-ch-ua-mobile"] ?? "?0";
    headers["sec-ch-ua-platform"] = headers["sec-ch-ua-platform"] ?? '"macOS"';

    callback({ requestHeaders: headers });
  });

  try {
    const dataDir = process.env.DATA_DIR ?? path.join(app.getPath("userData"), "omnidata");
    fs.mkdirSync(dataDir, { recursive: true });
    await startBackend(dataDir);
  } catch (error) {
    console.error("Unable to start backend:", error);
    try {
      backendProc?.kill();
    } catch (killError) {
      console.warn("Failed to terminate backend after startup error", killError);
    }
    app.quit();
    return;
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  try {
    backendProc?.kill();
  } catch (error) {
    console.warn("Failed to terminate backend process", error);
  }
});
