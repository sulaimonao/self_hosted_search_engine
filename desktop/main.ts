import {
  app,
  BrowserWindow,
  BrowserView,
  ipcMain,
  Menu,
  Rectangle,
  session,
  shell,
  WebContents,
} from 'electron';
import path from 'node:path';
import fs from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { randomUUID } from 'node:crypto';
import { TextDecoder } from 'node:util';

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

type BrowserNavError = {
  code?: number;
  description?: string;
};

type BrowserNavState = {
  tabId: string;
  url: string;
  title?: string | null;
  favicon?: string | null;
  canGoBack: boolean;
  canGoForward: boolean;
  isActive: boolean;
  isLoading: boolean;
  error?: BrowserNavError | null;
};

type BrowserTabList = {
  tabs: BrowserNavState[];
  activeTabId: string | null;
};

type BrowserTabRecord = {
  id: string;
  view: BrowserView;
  title: string | null;
  favicon?: string | null;
  lastUrl: string;
  isLoading: boolean;
  lastError?: BrowserNavError | null;
  pendingReferrer?: string | null;
  lastHistoryKey?: string | null;
  lastHistoryAt?: number | null;
};

type BrowserHistoryEntry = {
  id: number;
  url: string;
  title: string | null;
  visitTime: number;
  transition?: string | null;
  referrer?: string | null;
  tabId?: string;
};

type BrowserBounds = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type BrowserSettings = {
  thirdPartyCookies: boolean;
  searchMode: 'auto' | 'query';
  spellcheckLanguage: string;
  import {
    app,
    BrowserWindow,
    BrowserView,
    ipcMain,
    Menu,
    Rectangle,
    session,
    shell,
    WebContents,
  } from 'electron';
  import path from 'node:path';
  import fs from 'node:fs';
  import { pathToFileURL, fileURLToPath } from 'node:url';
  import { createRequire } from 'node:module';

  declare global {
    // eslint-disable-next-line no-var
    var __desktopLoggerHandlersRegistered: boolean | undefined;
  }
const sharedLogger = require('../shared/logger');
const log = sharedLogger.createComponentLogger('electron-main', { pid: process.pid });

if (!globalThis.__desktopLoggerHandlersRegistered) {
  process.on('uncaughtException', (error: Error) => {
    log.error('Uncaught exception in Electron main process', {
      message: error?.message,
      stack: error?.stack,
    });
  });
  process.on('unhandledRejection', (reason: unknown) => {
    if (reason instanceof Error) {
      log.error('Unhandled promise rejection in Electron main process', {
        message: reason.message,
        stack: reason.stack,
      });
      return;
    }
    let serialized: string;
    try {
      serialized = typeof reason === 'object' ? JSON.stringify(reason) : String(reason);
    } catch {
      serialized = String(reason);
    }
    log.error('Unhandled promise rejection in Electron main process', {
      reason: serialized,
    });
  });
  globalThis.__desktopLoggerHandlersRegistered = true;
}

const DEFAULT_FRONTEND_ORIGIN = (() => {
  const fallbackHost = 'localhost';
  const fallbackPort = '3100';
  const rawHost = process.env.FRONTEND_HOST;
  const host =
    typeof rawHost === 'string' && rawHost.trim().length > 0 ? rawHost.trim() : fallbackHost;
  const rawPort = process.env.FRONTEND_PORT;
  const parsedPort = rawPort ? Number.parseInt(rawPort, 10) : NaN;
  const port = Number.isFinite(parsedPort) && parsedPort > 0 ? String(parsedPort) : fallbackPort;
  const protocol =
    process.env.FRONTEND_PROTOCOL?.trim().toLowerCase() === 'https' ? 'https' : 'http';
  return `${protocol}://${host}:${port}`;
})();
const DEFAULT_API_URL = 'http://127.0.0.1:5050';
const FRONTEND_URL = process.env.APP_URL || process.env.FRONTEND_URL || DEFAULT_FRONTEND_ORIGIN;
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
const LLM_STREAM_INACTIVITY_MS = (() => {
  const raw = Number(process.env.LLM_STREAM_IDLE_TIMEOUT_MS);
  return Number.isFinite(raw) && raw > 0 ? raw : 30_000;
})();

type ActiveLlmStreamEntry = {
  controller: AbortController;
  requestId: string;
  timeoutId: ReturnType<typeof setTimeout> | null;
  tabId: string;
};

const activeLlmStreams = new Map<number, Map<string, ActiveLlmStreamEntry>>();

function normalizeTabKey(candidate: unknown, contentsId: number): string {
  if (typeof candidate === 'string') {
    const trimmed = candidate.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
  } else if (typeof candidate === 'number' && Number.isFinite(candidate)) {
    return String(candidate);
  }
  return `__wc:${contentsId}`;
}

function ensureLlmStreamRegistry(contentsId: number): Map<string, ActiveLlmStreamEntry> {
  let registry = activeLlmStreams.get(contentsId);
  if (!registry) {
    registry = new Map();
    activeLlmStreams.set(contentsId, registry);
  }
  return registry;
}

function clearLlmStreamTimer(entry?: ActiveLlmStreamEntry | null) {
  if (entry?.timeoutId) {
    clearTimeout(entry.timeoutId);
    entry.timeoutId = null;
  }
}

function detachLlmStream(
  contentsId: number,
  tabKey: string,
  entry?: ActiveLlmStreamEntry | null,
): void {
  clearLlmStreamTimer(entry);
  const registry = activeLlmStreams.get(contentsId);
  if (!registry) {
    return;
  }
  if (entry && registry.get(tabKey) !== entry) {
    return;
  }
  registry.delete(tabKey);
  if (registry.size === 0) {
    activeLlmStreams.delete(contentsId);
  }
}

function findLlmStreamByRequestId(
  registry: Map<string, ActiveLlmStreamEntry>,
  requestId: string,
): { tabKey: string; entry: ActiveLlmStreamEntry } | null {
  for (const [tabKey, entry] of registry) {
    if (entry.requestId === requestId) {
      return { tabKey, entry };
    }
  }
  return null;
}

function flushSseBuffer(target: WebContents, requestId: string, buffer: string): string {
  let working = buffer;
  let index = working.indexOf("\n\n");
  while (index !== -1) {
    const frame = working.slice(0, index);
    working = working.slice(index + 2);
    if (frame.trim()) {
      target.send('llm:frame', { requestId, frame });
    }
    index = working.indexOf("\n\n");
  }
  return working;
}

function sendSseError(target: WebContents, requestId: string, payload: Record<string, unknown>) {
  target.send('llm:frame', {
    requestId,
    frame: `data: ${JSON.stringify(payload)}\n\n`,
  });
}

const isDev = !app.isPackaged;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

app.setAppLogsPath();

const MAIN_SESSION_KEY = 'persist:main';
const DESKTOP_USER_AGENT =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36';
const RESOLVED_USER_AGENT = (() => {
  const candidate = process.env.DESKTOP_USER_AGENT;
  if (typeof candidate === 'string') {
    const trimmed = candidate.trim();
    if (trimmed.length > 0) {
      return trimmed;
    }
  }
  return DESKTOP_USER_AGENT;
})();
const DEFAULT_TAB_URL = `${FRONTEND_URL}/graph`;
const DEFAULT_TAB_TITLE = 'New Tab';
const DEFAULT_BOUNDS: Rectangle = { x: 0, y: 136, width: 1280, height: 720 };
const NAV_STATE_CHANNEL = 'nav:state';
const TAB_LIST_CHANNEL = 'browser:tabs';
const HISTORY_CHANNEL = 'browser:history';
const SETTINGS_CHANNEL = 'settings:state';
const DEFAULT_SETTINGS: BrowserSettings = {
  thirdPartyCookies: true,
  searchMode: 'auto',
  spellcheckLanguage: 'en-US',
  proxy: { mode: 'system', host: '', port: '' },
  openSearchExternally: false,
};
const FALLBACK_SPELLCHECK_LANGUAGES = ['en-US', 'en-GB'];
const MAX_HISTORY_ENTRIES = 500;
const FRONTEND_ORIGIN = (() => {
  try {
    return new URL(FRONTEND_URL).origin;
  } catch {
    return null;
  }
})();

let win: BrowserWindow | null = null;
let lastSystemCheck: SystemCheckResult = null;
let initialSystemCheckPromise: Promise<SystemCheckResult> | null = null;

const tabs = new Map<string, BrowserTabRecord>();
const tabOrder: string[] = [];
let activeTabId: string | null = null;
let browserContentBounds: Rectangle = { ...DEFAULT_BOUNDS };
const runtimeNetworkState: { acceptLanguage: string | null } = {
  acceptLanguage: null,
};
let runtimeSettings: BrowserSettings = { ...DEFAULT_SETTINGS };
let settingsFilePath: string | null = null;
let cachedSystemSpellcheckLanguages: string[] | null = null;
const permissionHandlerSessions = new WeakSet<Electron.Session>();
const historyEntries: BrowserHistoryEntry[] = [];
let historySeq = 1;

function formatAcceptLanguageHeader(value: string | null | undefined): string | null {
  const normalized = normalizeLanguageCode(value);
  if (!normalized) {
    return null;
  }
  const [primary] = normalized.split('-');
  if (primary && primary.length && primary.toLowerCase() !== normalized.toLowerCase()) {
    return `${normalized},${primary};q=0.9`;
  }
  return normalized;
}

function updateRuntimeAcceptLanguage(locale?: string | null) {
  const formatted = formatAcceptLanguageHeader(locale ?? null);
  if (formatted) {
    runtimeNetworkState.acceptLanguage = formatted;
    return;
  }
  const fallback = typeof app.getLocale === 'function' ? app.getLocale() : null;
  runtimeNetworkState.acceptLanguage = formatAcceptLanguageHeader(fallback);
}

function normalizeLanguageCode(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  try {
    const [canonical] = Intl.getCanonicalLocales(trimmed);
    if (canonical) {
      return canonical;
    }
  } catch {
    // ignore invalid locales
  }
  return trimmed.replace(/_/g, '-');
}

function normalizeLanguageList(values: unknown): string[] {
  const normalized: string[] = [];
  const addValue = (candidate: unknown) => {
    const normalizedValue = normalizeLanguageCode(candidate);
    if (normalizedValue) {
      normalized.push(normalizedValue);
    }
  };
  if (Array.isArray(values)) {
    values.forEach(addValue);
  } else if (values) {
    addValue(values);
  }
  return Array.from(new Set(normalized));
}

function collectSpellcheckLanguages(sourceList: unknown): string[] {
  const normalized = normalizeLanguageList(sourceList);
  const seen = new Set(normalized);
  const addValue = (value: unknown) => {
    const normalizedValue = normalizeLanguageCode(value);
    if (normalizedValue && !seen.has(normalizedValue)) {
      seen.add(normalizedValue);
      normalized.push(normalizedValue);
    }
  };
  addValue(runtimeSettings?.spellcheckLanguage);
  FALLBACK_SPELLCHECK_LANGUAGES.forEach(addValue);
  return normalized;
}

function getSystemSpellcheckLanguages(): string[] {
  if (Array.isArray(cachedSystemSpellcheckLanguages)) {
    return cachedSystemSpellcheckLanguages;
  }
  const sess = session.fromPartition(MAIN_SESSION_KEY);
  const spellcheckSession = sess as Electron.Session & {
    availableSpellCheckerLanguages?: () => string[] | undefined;
  };
  if (spellcheckSession && typeof spellcheckSession.availableSpellCheckerLanguages === 'function') {
    try {
      const available = spellcheckSession.availableSpellCheckerLanguages();
      cachedSystemSpellcheckLanguages = normalizeLanguageList(Array.isArray(available) ? available : []);
      return cachedSystemSpellcheckLanguages;
    } catch (error) {
      log.warn('Failed to enumerate spellcheck languages', { error });
    }
  }
  cachedSystemSpellcheckLanguages = [];
  return cachedSystemSpellcheckLanguages;
}

function listAvailableSpellcheckLanguages(): string[] {
  const baseLanguages = getSystemSpellcheckLanguages();
  return collectSpellcheckLanguages(baseLanguages);
}

function resolveSettingsStorePath(): string | null {
  if (settingsFilePath) {
    return settingsFilePath;
  }
  if (!app.isReady()) {
    return null;
  }
  try {
    settingsFilePath = path.join(app.getPath('userData'), 'browser-settings.json');
    return settingsFilePath;
  } catch (error) {
    log.warn('Failed to resolve browser settings path', { error });
    return null;
  }
}

function emitSettingsState() {
  if (runtimeSettings) {
    sendToRenderer(SETTINGS_CHANNEL, runtimeSettings);
  }
}

function persistRuntimeSettings() {
  const targetPath = resolveSettingsStorePath();
  if (!targetPath || !runtimeSettings) {
    return;
  }
  try {
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, JSON.stringify(runtimeSettings, null, 2), 'utf8');
  } catch (error) {
    log.warn('Failed to persist browser settings', { error });
  }
}

function normalizeSettings(candidate: Partial<BrowserSettings> | null | undefined): BrowserSettings {
  const base: BrowserSettings = {
    ...DEFAULT_SETTINGS,
    proxy: { ...DEFAULT_SETTINGS.proxy },
  };
  if (!candidate || typeof candidate !== 'object') {
    return base;
  }
  if (typeof candidate.thirdPartyCookies === 'boolean') {
    base.thirdPartyCookies = candidate.thirdPartyCookies;
  }
  if (candidate.searchMode === 'auto' || candidate.searchMode === 'query') {
    base.searchMode = candidate.searchMode;
  }
  if (typeof candidate.spellcheckLanguage === 'string' && candidate.spellcheckLanguage.trim()) {
    base.spellcheckLanguage = candidate.spellcheckLanguage.trim();
  }
  if (typeof candidate.openSearchExternally === 'boolean') {
    base.openSearchExternally = candidate.openSearchExternally;
  }
  if (candidate.proxy && typeof candidate.proxy === 'object') {
    const mode: 'manual' | 'system' = candidate.proxy.mode === 'manual' ? 'manual' : 'system';
    const host = typeof candidate.proxy.host === 'string' ? candidate.proxy.host : '';
    const port = Number.isFinite(Number(candidate.proxy.port)) ? String(candidate.proxy.port) : '';
    base.proxy = { mode, host, port };
  }
  return base;
}

function loadRuntimeSettings() {
  const targetPath = resolveSettingsStorePath();
  if (!targetPath) {
    runtimeSettings = { ...DEFAULT_SETTINGS };
    return;
  }
  try {
    if (fs.existsSync(targetPath)) {
      const raw = fs.readFileSync(targetPath, 'utf8');
      const parsed = JSON.parse(raw);
      runtimeSettings = normalizeSettings(parsed);
      return;
    }
  } catch (error) {
    log.warn('Failed to load browser settings', { error });
  }
  runtimeSettings = { ...DEFAULT_SETTINGS };
}

function mergeSettings(
  base: BrowserSettings,
  patch: Partial<BrowserSettings> | null | undefined,
): BrowserSettings {
  if (!patch || typeof patch !== 'object') {
    return base;
  }
  const next: Partial<BrowserSettings> = {
    ...base,
    ...patch,
    proxy: {
      ...base.proxy,
      ...(patch.proxy ?? {}),
    },
  };
  return normalizeSettings(next);
}

function applySpellcheckSettings(sess: Electron.Session | null, language: string | undefined) {
  updateRuntimeAcceptLanguage(language);
  if (!sess || !language) {
    return;
  }
  try {
    sess.setSpellCheckerLanguages([language]);
  } catch (error) {
    log.warn('Failed to apply spellcheck language', { error });
  }
}

async function applyProxySettings(sess: Electron.Session | null, proxy: BrowserSettings['proxy']) {
  if (!sess || !proxy) {
    return;
  }
  if (proxy.mode === 'manual') {
    const host = (proxy.host || '').trim();
    const portValue = Number(proxy.port);
    if (host && Number.isFinite(portValue) && portValue > 0) {
      const proxyRules = `${host}:${portValue}`;
      try {
        await sess.setProxy({ proxyRules });
        return;
      } catch (error) {
        log.warn('Failed to apply manual proxy', { error });
      }
    }
  }
  try {
    await sess.setProxy({ mode: 'system' });
  } catch (error) {
    log.warn('Failed to reset proxy settings', { error });
  }
}

async function applyRuntimeSettingsToSession(targetSession?: Electron.Session | null) {
  const sess = targetSession ?? session.fromPartition(MAIN_SESSION_KEY);
  if (!sess || !runtimeSettings) {
    return;
  }
  applySpellcheckSettings(sess, runtimeSettings.spellcheckLanguage);
  await applyProxySettings(sess, runtimeSettings.proxy);
}

async function updateRuntimeSettings(patch: Partial<BrowserSettings> | null | undefined) {
  runtimeSettings = mergeSettings(runtimeSettings ?? DEFAULT_SETTINGS, patch);
  persistRuntimeSettings();
  emitSettingsState();
  await applyRuntimeSettingsToSession();
}

function registerPermissionHandlers(sess: Electron.Session | null) {
  if (!sess || permissionHandlerSessions.has(sess)) {
    return;
  }
  permissionHandlerSessions.add(sess);
  sess.setPermissionCheckHandler((_wc, permission, requestingOrigin, details) => {
    const permissionName = permission as unknown as string;
    if (permissionName !== 'cookies') {
      return true;
    }
    if (!runtimeSettings || runtimeSettings.thirdPartyCookies) {
      return true;
    }
    const embeddingOrigin = details?.embeddingOrigin || requestingOrigin;
    if (!embeddingOrigin || embeddingOrigin === requestingOrigin) {
      return true;
    }
    return false;
  });
}

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
  const target = getMainWindow();
  target?.webContents.send(channel, payload);
}

function getMainWindow(): BrowserWindow | null {
  if (win && !win.isDestroyed()) {
    return win;
  }
  return null;
}

function sendToRenderer(channel: string, payload: unknown) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  target.webContents.send(channel, payload);
}

async function safeJson<T = unknown>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

function getActiveTab(): BrowserTabRecord | undefined {
  if (!activeTabId) {
    return undefined;
  }
  return tabs.get(activeTabId);
}

function buildNavState(tab: BrowserTabRecord): BrowserNavState {
  const wc = tab.view.webContents;
  const currentUrl = wc.getURL() || tab.lastUrl || 'about:blank';
  return {
    tabId: tab.id,
    url: currentUrl,
    title: tab.title ?? null,
    favicon: tab.favicon ?? null,
    canGoBack: wc.canGoBack(),
    canGoForward: wc.canGoForward(),
    isActive: activeTabId === tab.id,
    isLoading: tab.isLoading,
    error: tab.lastError ?? null,
  };
}

function emitNavState(tab: BrowserTabRecord) {
  sendToRenderer(NAV_STATE_CHANNEL, buildNavState(tab));
}

function snapshotTabList(): BrowserTabList {
  const list: BrowserNavState[] = [];
  for (const id of tabOrder) {
    const tab = tabs.get(id);
    if (tab) {
      list.push(buildNavState(tab));
    }
  }
  return {
    tabs: list,
    activeTabId,
  };
}

function emitTabList() {
  sendToRenderer(TAB_LIST_CHANNEL, snapshotTabList());
}

function normalizeHistoryUrl(raw: string | null | undefined): string | null {
  if (typeof raw !== 'string') {
    return null;
  }
  const trimmed = raw.trim();
  if (!trimmed || trimmed === 'about:blank') {
    return null;
  }
  const lowered = trimmed.toLowerCase();
  if (
    lowered.startsWith('chrome://') ||
    lowered.startsWith('devtools://') ||
    lowered.startsWith('about:') ||
    lowered.startsWith('file://') ||
    lowered.startsWith('app://')
  ) {
    return null;
  }
  try {
    const parsed = new URL(trimmed);
    if (FRONTEND_ORIGIN && parsed.origin === FRONTEND_ORIGIN) {
      return null;
    }
  } catch {
    if (!/^https?:/i.test(trimmed)) {
      return null;
    }
  }
  return trimmed;
}

function emitHistoryEntry(entry: BrowserHistoryEntry) {
  sendToRenderer(HISTORY_CHANNEL, entry);
}

async function syncHistoryEntry(entry: BrowserHistoryEntry): Promise<void> {
  const payload: Record<string, unknown> = {
    url: entry.url,
    title: entry.title,
    visited_at: new Date(entry.visitTime).toISOString(),
    tab_id: entry.tabId,
  };
  if (entry.referrer) {
    payload.referrer = entry.referrer;
  }
  try {
    await fetch(`${API_BASE_URL}/api/history/visit`, {
      method: 'POST',
      headers: JSON_HEADERS,
      body: JSON.stringify(payload),
    });
  } catch (error) {
    log.debug('history.visit_failed', { error });
  }
}

async function recordHistoryVisit(tab: BrowserTabRecord, url: string, referrer?: string | null) {
  const normalizedUrl = normalizeHistoryUrl(url);
  if (!normalizedUrl) {
    return;
  }
  const visitTime = Date.now();
  const historyKey = `${tab.id}:${normalizedUrl}`;
  if (tab.lastHistoryKey === historyKey && tab.lastHistoryAt && visitTime - tab.lastHistoryAt < 750) {
    return;
  }
  tab.lastHistoryKey = historyKey;
  tab.lastHistoryAt = visitTime;
  const wcTitle = (() => {
    try {
      return tab.view.webContents.getTitle();
    } catch {
      return null;
    }
  })();
  const entry: BrowserHistoryEntry = {
    id: historySeq++,
    url: normalizedUrl,
    title: tab.title ?? wcTitle ?? null,
    visitTime,
    referrer: referrer ?? tab.pendingReferrer ?? undefined,
    tabId: tab.id,
  };
  tab.pendingReferrer = null;
  historyEntries.push(entry);
  if (historyEntries.length > MAX_HISTORY_ENTRIES) {
    historyEntries.shift();
  }
  emitHistoryEntry(entry);
  void syncHistoryEntry(entry);
}

function sanitizeBounds(bounds: BrowserBounds): Rectangle {
  const safe: Rectangle = {
    x: Number.isFinite(bounds.x) ? Math.max(0, Math.round(bounds.x)) : 0,
    y: Number.isFinite(bounds.y) ? Math.max(0, Math.round(bounds.y)) : 0,
    width: Number.isFinite(bounds.width) ? Math.max(0, Math.round(bounds.width)) : 0,
    height: Number.isFinite(bounds.height) ? Math.max(0, Math.round(bounds.height)) : 0,
  };

  if ((safe.width === 0 || safe.height === 0) && getMainWindow()) {
    const content = getMainWindow()!.getContentBounds();
    if (safe.width === 0) {
      safe.width = Math.max(0, content.width - safe.x);
    }
    if (safe.height === 0) {
      safe.height = Math.max(0, content.height - safe.y);
    }
  }

  if (safe.width === 0) {
    safe.width = DEFAULT_BOUNDS.width;
  }
  if (safe.height === 0) {
    safe.height = DEFAULT_BOUNDS.height;
  }
  return safe;
}

function applyBoundsToView(view: BrowserView) {
  const bounds = browserContentBounds;
  view.setBounds(bounds);
  view.setAutoResize({ width: true, height: true });
}

function updateBrowserBounds(bounds: BrowserBounds) {
  browserContentBounds = sanitizeBounds(bounds);
  const active = getActiveTab();
  if (active) {
    applyBoundsToView(active.view);
  }
}

function attachTab(tab: BrowserTabRecord) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  try {
    target.setBrowserView(tab.view);
    applyBoundsToView(tab.view);
    tab.view.webContents.focus();
  } catch (error) {
    log.warn('Failed to attach BrowserView', { tabId: tab.id, error });
  }
}

function detachTab(tab: BrowserTabRecord) {
  const target = getMainWindow();
  if (!target) {
    return;
  }
  try {
    target.removeBrowserView(tab.view);
  } catch (error) {
    log.warn('Failed to detach BrowserView', { tabId: tab.id, error });
  }
}

function setActiveTab(tabId: string) {
  const next = tabs.get(tabId);
  if (!next) {
    return;
  }

  if (activeTabId === tabId) {
    attachTab(next);
    emitNavState(next);
    emitTabList();
    return;
  }

  const previous = getActiveTab();
  if (previous) {
    detachTab(previous);
  }

  activeTabId = tabId;
  attachTab(next);
  emitNavState(next);
  emitTabList();
}

function ensureTabOrder(tabId: string) {
  if (!tabOrder.includes(tabId)) {
    tabOrder.push(tabId);
  }
}

function resolveTabFromId(tabId: unknown): BrowserTabRecord | undefined {
  if (typeof tabId === 'string' && tabId) {
    return tabs.get(tabId);
  }
  return getActiveTab();
}

function handleTabLifecycle(tab: BrowserTabRecord) {
  const { webContents: wc } = tab.view;

  wc.setWindowOpenHandler(({ url }) => {
    if (typeof url === 'string' && url.trim().length > 0) {
      void createBrowserTab(url, { activate: true });
    }
    return { action: 'deny' };
  });

  wc.on('did-start-navigation', (_event, url, _isInPlace, isMainFrame) => {
    if (!isMainFrame) {
      return;
    }
    tab.pendingReferrer = tab.lastUrl;
    tab.isLoading = true;
    tab.lastError = null;
    tab.lastUrl = url;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-navigate', (_event, url) => {
    const referrer = tab.pendingReferrer ?? undefined;
    tab.lastUrl = url;
    tab.isLoading = false;
    tab.lastError = null;
    emitNavState(tab);
    emitTabList();
    void recordHistoryVisit(tab, url, referrer);
  });

  wc.on('did-navigate-in-page', (_event, url) => {
    const referrer = tab.lastUrl;
    tab.lastUrl = url;
    emitNavState(tab);
    emitTabList();
    void recordHistoryVisit(tab, url, referrer);
  });

  wc.on('did-stop-loading', () => {
    if (tab.isLoading) {
      tab.isLoading = false;
      emitNavState(tab);
      emitTabList();
    }
  });

  wc.on('page-title-updated', (_event, title) => {
    tab.title = title || DEFAULT_TAB_TITLE;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('page-favicon-updated', (_event, favicons) => {
    tab.favicon = Array.isArray(favicons) && favicons.length > 0 ? favicons[0] ?? null : null;
    emitNavState(tab);
    emitTabList();
  });

  wc.on('did-fail-load', (_event, errorCode, errorDescription, _validatedURL, isMainFrame) => {
    if (!isMainFrame || errorCode === -3) {
      return;
    }
    tab.isLoading = false;
    tab.lastError = {
      code: errorCode,
      description: errorDescription || 'Navigation failed',
    };
    emitNavState(tab);
    emitTabList();
  });
}

async function createBrowserTab(url?: string, options: { activate?: boolean } = {}): Promise<BrowserNavState> {
  const id = randomUUID();
  const view = new BrowserView({
    webPreferences: {
      partition: MAIN_SESSION_KEY,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
  });

  view.webContents.setUserAgent(RESOLVED_USER_AGENT);

  const tab: BrowserTabRecord = {
    id,
    view,
    title: DEFAULT_TAB_TITLE,
    favicon: null,
    lastUrl: DEFAULT_TAB_URL,
    isLoading: false,
    lastError: null,
    pendingReferrer: null,
    lastHistoryKey: null,
    lastHistoryAt: null,
  };

  tabs.set(id, tab);
  ensureTabOrder(id);
  handleTabLifecycle(tab);

  if (options.activate !== false) {
    setActiveTab(id);
  }

  const targetUrl = typeof url === 'string' && url.trim().length > 0 ? url.trim() : DEFAULT_TAB_URL;
  tab.lastUrl = targetUrl;
  tab.isLoading = true;
  emitNavState(tab);
  emitTabList();

  try {
    await view.webContents.loadURL(targetUrl);
  } catch (error) {
    log.warn('Failed to load tab URL', { url: targetUrl, error });
    tab.isLoading = false;
    tab.lastError = {
      description: error instanceof Error ? error.message : String(error),
    };
    emitNavState(tab);
  }

  return buildNavState(tab);
}

function closeBrowserTab(tabId: string): boolean {
  const tab = tabs.get(tabId);
  if (!tab) {
    return false;
  }

  const index = tabOrder.indexOf(tabId);
  if (index >= 0) {
    tabOrder.splice(index, 1);
  }

  const wasActive = activeTabId === tabId;
  if (wasActive) {
    detachTab(tab);
  }

  tabs.delete(tabId);

  try {
    const { view } = tab;
    const { webContents } = view;
    if (webContents && !webContents.isDestroyed()) {
      webContents.removeAllListeners();
      webContents.stop();
      (webContents as Electron.WebContents & { destroy?: () => void }).destroy?.();
    }
    (view as BrowserView & { destroy?: () => void }).destroy?.();
  } catch (error) {
    log.warn('Failed to destroy BrowserView resources', { tabId, error });
  }

  if (wasActive) {
    activeTabId = null;
    const fallbackId = tabOrder[index] ?? tabOrder[index - 1] ?? tabOrder[0] ?? null;
    if (fallbackId) {
      setActiveTab(fallbackId);
    }
  }

  if (tabOrder.length === 0) {
    void createBrowserTab(DEFAULT_TAB_URL, { activate: true }).catch((error) => {
      log.error('Failed to create fallback tab', error);
    });
  } else {
    emitTabList();
  }

  return true;
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
  const target = resolveFrontendTarget();
  log.info('Creating primary BrowserWindow', { target });
  win = new BrowserWindow({
    width: 1366,
    height: 900,
    show: false,
    title: 'Personal Search Engine',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      partition: MAIN_SESSION_KEY,
      webviewTag: true,
      spellcheck: true,
    },
  });

  win.once('ready-to-show', () => {
    log.info('Main window ready to show');
    win?.show();
    emitSettingsState();
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      void createBrowserTab(url, { activate: true });
    }
    return { action: 'deny' };
  });

  win.on('resize', () => {
    const active = getActiveTab();
    if (active) {
      applyBoundsToView(active.view);
    }
  });

  win
    .loadURL(target)
    .catch((error) => {
      log.error('Failed to load frontend', {
        message: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined,
      });
    });

  win.on('closed', () => {
    log.info('Browser window closed; cleaning up tabs');
    for (const [tabId, tab] of tabs) {
      try {
        if (!tab.view.webContents.isDestroyed()) {
          tab.view.webContents.removeAllListeners();
          tab.view.webContents.stop();
        }
      } catch (error) {
        log.warn('Failed to clean up tab during window close', { tabId, error });
      }
    }
    tabs.clear();
    tabOrder.splice(0, tabOrder.length);
    activeTabId = null;
    win = null;
  });
}

app.whenReady().then(async () => {
  log.info('Electron app ready; preparing browser session');
  loadRuntimeSettings();
  const mainSession = session.fromPartition(MAIN_SESSION_KEY);
  mainSession.setUserAgent(RESOLVED_USER_AGENT);
  registerPermissionHandlers(mainSession);
  updateRuntimeAcceptLanguage(runtimeSettings?.spellcheckLanguage || app.getLocale());
  await applyRuntimeSettingsToSession(mainSession);

  mainSession.webRequest.onBeforeSendHeaders((details, callback) => {
    const acceptLanguageHeader =
      details.requestHeaders['Accept-Language'] ??
      details.requestHeaders['accept-language'];

    const hintKeys = [
      'sec-ch-ua',
      'sec-ch-ua-mobile',
      'sec-ch-ua-platform',
      'sec-ch-ua-arch',
      'sec-ch-ua-model',
      'sec-ch-ua-platform-version',
      'sec-ch-ua-full-version-list',
    ];

    const headers: Record<string, string | string[]> = {
      ...details.requestHeaders,
      'User-Agent': RESOLVED_USER_AGENT,
    };

    if (acceptLanguageHeader) {
      headers['Accept-Language'] = acceptLanguageHeader;
      runtimeNetworkState.acceptLanguage = formatAcceptLanguageHeader(acceptLanguageHeader) ?? acceptLanguageHeader;
    }

    for (const key of hintKeys) {
      const value =
        details.requestHeaders[key] ?? details.requestHeaders[key.toUpperCase()];
      if (value != null) {
        headers[key] = value;
      }
    }

    headers['sec-ch-ua'] =
      headers['sec-ch-ua'] ??
      '"Chromium";v="120", "Not A(Brand";v="99"';
    headers['sec-ch-ua-mobile'] =
      headers['sec-ch-ua-mobile'] ?? '?0';
    headers['sec-ch-ua-platform'] =
      headers['sec-ch-ua-platform'] ?? '"macOS"';

    if (!headers['Accept-Language']) {
      headers['Accept-Language'] = runtimeNetworkState.acceptLanguage || app.getLocale();
    }

    callback({ requestHeaders: headers });
  });

  mainSession.webRequest.onHeadersReceived((details, callback) => {
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
  browserContentBounds = sanitizeBounds(browserContentBounds);
  if (!tabs.size) {
    await createBrowserTab(DEFAULT_TAB_URL, { activate: true });
  }

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
    log.info('Electron app activate event received');
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  log.info('All BrowserWindows closed');
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle('settings:get', async () => runtimeSettings);

ipcMain.handle('settings:update', async (_event, patch: Partial<BrowserSettings> | null | undefined) => {
  await updateRuntimeSettings(patch);
  return runtimeSettings;
});

ipcMain.handle('settings:list-spellcheck-languages', async () => listAvailableSpellcheckLanguages());

ipcMain.handle(
  'llm:stream',
  async (
    event,
    payload:
      | { requestId?: string | null; body?: Record<string, unknown> | null; tabId?: string | null }
      | undefined,
  ) => {
    const sender = event.sender;
    const contentsId = sender.id;
    const baseId = typeof payload?.requestId === 'string' ? payload.requestId.trim() : '';
    const requestId = baseId || randomUUID();
    const rawBody = payload?.body && typeof payload.body === 'object' ? payload.body : {};
    const body: Record<string, unknown> = { ...(rawBody as Record<string, unknown>) };
    if (typeof body['request_id'] !== 'string') {
      body['request_id'] = requestId;
    }
    body['stream'] = true;

    const controller = new AbortController();
    const tabKey = normalizeTabKey(
      payload?.tabId ?? (body['tab_id'] as string | number | undefined),
      contentsId,
    );
    const registry = ensureLlmStreamRegistry(contentsId);
    const existing = registry.get(tabKey);
    if (existing) {
      existing.controller.abort();
      clearLlmStreamTimer(existing);
    }
    const entry: ActiveLlmStreamEntry = { controller, requestId, timeoutId: null, tabId: tabKey };
    registry.set(tabKey, entry);
    let timedOut = false;

    const scheduleInactivityTimer = () => {
      clearLlmStreamTimer(entry);
      entry.timeoutId = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, LLM_STREAM_INACTIVITY_MS);
    };

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { ...JSON_HEADERS, Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok || !response.body) {
        sendSseError(sender, requestId, {
          type: 'error',
          error: response.ok ? 'stream_unavailable' : `http_${response.status}`,
          status: response.status,
        });
        return { ok: false, status: response.status };
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      scheduleInactivityTimer();
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        scheduleInactivityTimer();
        buffer += decoder.decode(value, { stream: true });
        buffer = flushSseBuffer(sender, requestId, buffer);
      }
      clearLlmStreamTimer(entry);
      buffer += decoder.decode();
      flushSseBuffer(sender, requestId, buffer);
      return { ok: true };
    } catch (error) {
      const aborted = controller.signal.aborted;
      const fallbackMessage =
        error instanceof Error ? error.message : String(error ?? 'stream_failed');
      const errorCode = timedOut ? 'timeout' : fallbackMessage;
      const errorPayload: Record<string, unknown> = {
        type: 'error',
        error: timedOut ? 'timeout' : aborted ? 'aborted' : fallbackMessage,
      };
      if (timedOut) {
        errorPayload['hint'] = `LLM stream idle for ${
          Math.round(LLM_STREAM_INACTIVITY_MS / 1000)
        }s`;
        errorPayload['timeout_ms'] = LLM_STREAM_INACTIVITY_MS;
      }
      sendSseError(sender, requestId, errorPayload);
      return { ok: false, error: errorCode, aborted, timeout: timedOut };
    } finally {
      const current = registry.get(tabKey);
      if (current === entry) {
        detachLlmStream(contentsId, tabKey, entry);
      } else {
        clearLlmStreamTimer(entry);
      }
    }
  },
);

ipcMain.handle(
  'llm:abort',
  (
    event,
    payload:
      | { requestId?: string | null; tabId?: string | null }
      | string
      | null
      | undefined,
  ) => {
    const contentsId = event.sender.id;
    const registry = activeLlmStreams.get(contentsId);
    if (!registry || registry.size === 0) {
      return { ok: false, active: false };
    }
    let requestedId: string | null = null;
    let requestedTab: string | null = null;
    if (typeof payload === 'string') {
      const trimmed = payload.trim();
      requestedId = trimmed || null;
    } else if (payload === null || payload === undefined) {
      requestedId = null;
    } else if (typeof payload === 'object') {
      if ('requestId' in payload) {
        const raw = payload.requestId;
        if (typeof raw === 'string') {
          const trimmed = raw.trim();
          requestedId = trimmed || null;
        } else if (raw === null) {
          requestedId = null;
        }
      }
      if ('tabId' in payload) {
        const rawTab = payload.tabId;
        if (typeof rawTab === 'string') {
          const trimmedTab = rawTab.trim();
          requestedTab = trimmedTab || null;
        } else if (rawTab === null) {
          requestedTab = null;
        }
      }
    }

    let targetEntry: ActiveLlmStreamEntry | undefined;
    let tabKey: string | null = null;
    if (requestedTab) {
      tabKey = requestedTab;
      targetEntry = registry.get(tabKey);
    }
    if (!targetEntry && requestedId) {
      const match = findLlmStreamByRequestId(registry, requestedId);
      if (match) {
        tabKey = match.tabKey;
        targetEntry = match.entry;
      }
    }
    if (!targetEntry && !requestedId && registry.size === 1) {
      const iterator = registry.entries().next();
      if (!iterator.done) {
        const [onlyKey, onlyEntry] = iterator.value;
        tabKey = onlyKey;
        targetEntry = onlyEntry;
      }
    }

    if (!targetEntry || !tabKey) {
      if (requestedId) {
        return { ok: false, mismatch: true };
      }
      return { ok: false, active: false };
    }
    targetEntry.controller.abort();
    detachLlmStream(contentsId, tabKey, targetEntry);
    return { ok: true };
  },
);

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

ipcMain.handle('browser:create-tab', async (_event, payload: { url?: string } | undefined) => {
  const url = typeof payload?.url === 'string' ? payload.url : undefined;
  return createBrowserTab(url, { activate: true });
});

ipcMain.handle('browser:close-tab', async (_event, payload: { tabId?: string } | undefined) => {
  const tabId = typeof payload?.tabId === 'string' ? payload.tabId : '';
  return { ok: tabId ? closeBrowserTab(tabId) : false };
});

ipcMain.handle('browser:request-tabs', async () => snapshotTabList());

ipcMain.handle('browser:request-history', async (_event, payload: { limit?: number } | number | null | undefined) => {
  const rawLimit = typeof payload === 'number' ? payload : typeof payload === 'object' && payload !== null ? payload.limit : undefined;
  const limit = Number.isFinite(rawLimit) ? Math.max(1, Math.min(Number(rawLimit), MAX_HISTORY_ENTRIES)) : 100;
  const slice = historyEntries.slice(-limit);
  return slice.reverse();
});

ipcMain.on('browser:set-active', (_event, tabId: unknown) => {
  if (typeof tabId === 'string' && tabId) {
    setActiveTab(tabId);
  }
});

ipcMain.on('browser:bounds', (_event, bounds: BrowserBounds) => {
  if (bounds && typeof bounds === 'object') {
    updateBrowserBounds(bounds);
  }
});

ipcMain.on('nav:navigate', (_event, payload: { url?: string; tabId?: string | null } | undefined) => {
  const url = typeof payload?.url === 'string' ? payload.url.trim() : '';
  if (!url) {
    return;
  }
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  tab.lastError = null;
  tab.lastUrl = url;
  emitNavState(tab);
  void tab.view.webContents.loadURL(url).catch((error) => {
    log.warn('Failed to navigate tab', { tabId: tab.id, url, error });
    tab.isLoading = false;
    tab.lastError = {
      description: error instanceof Error ? error.message : String(error),
    };
    emitNavState(tab);
  });
});

ipcMain.on('nav:back', (_event, payload: { tabId?: string | null } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoBack()) {
    tab.view.webContents.goBack();
  }
  emitNavState(tab);
});

ipcMain.on('nav:forward', (_event, payload: { tabId?: string | null } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  if (tab.view.webContents.canGoForward()) {
    tab.view.webContents.goForward();
  }
  emitNavState(tab);
});

ipcMain.on('nav:reload', (_event, payload: { tabId?: string | null; ignoreCache?: boolean } | undefined) => {
  const tab = resolveTabFromId(payload?.tabId ?? null);
  if (!tab) {
    return;
  }
  tab.isLoading = true;
  try {
    if (payload?.ignoreCache) {
      tab.view.webContents.reloadIgnoringCache();
    } else {
      tab.view.webContents.reload();
    }
  } catch (error) {
    log.warn('Failed to reload tab', { tabId: tab.id, error });
    tab.isLoading = false;
  }
  emitNavState(tab);
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
