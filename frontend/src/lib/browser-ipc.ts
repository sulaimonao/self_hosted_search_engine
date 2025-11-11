"use client";

export type BrowserNavError = {
  code?: number;
  description?: string;
};

export type BrowserNavState = {
  tabId: string;
  url: string;
  title?: string | null;
  favicon?: string | null;
  canGoBack: boolean;
  canGoForward: boolean;
  isActive: boolean;
  isLoading?: boolean;
  error?: BrowserNavError | null;
  sessionPartition?: string | null;
  isIncognito?: boolean;
};

export type BrowserTabList = {
  tabs: BrowserNavState[];
  activeTabId: string | null;
};

export type BrowserHistoryEntry = {
  id: number;
  url: string;
  title: string | null;
  visitTime: number;
  transition?: string | null;
  referrer?: string | null;
  tabId?: string;
};

export type BrowserDownloadState = {
  id: string;
  url: string;
  filename?: string | null;
  mime?: string | null;
  bytesTotal?: number | null;
  bytesReceived?: number | null;
  path?: string | null;
  state: "in_progress" | "completed" | "cancelled" | "interrupted";
  startedAt?: number | null;
  completedAt?: number | null;
};

export type BrowserSettings = {
  thirdPartyCookies: boolean;
  searchMode: "auto" | "query";
  spellcheckLanguage: string;
  proxy: {
    mode: "system" | "manual";
    host?: string;
    port?: string;
  };
  openSearchExternally: boolean;
};

export type BrowserPermissionPrompt = {
  id: string;
  origin: string;
  permission: string;
};

export type BrowserPermissionState = {
  origin: string;
  permissions: { permission: string; setting: string; updatedAt: number }[];
};

export type BrowserDiagnosticsReport = {
  timestamp: number;
  userAgent: string | null;
  navigatorLanguage: string | null;
  navigatorLanguages: string[];
  platform: string | null;
  uaCh: Record<string, unknown> | null;
  uaChError: string | null;
  uaData: Record<string, unknown> | null;
  uaDataError: string | null;
  webdriver: boolean | null | undefined;
  webdriverError: string | null;
  webgl: { vendor: string | null; renderer: string | null; error: string | null };
  cookies: { count: number | null; raw: string | null; error: string | null };
  serviceWorker: {
    supported: boolean;
    status: string;
    registrations: number;
    scopes: string[];
    error: string | null;
  };
};

export type BrowserDiagnosticsResult = {
  ok: boolean;
  data?: BrowserDiagnosticsReport | null;
  error?: string | null;
};

export type ClearBrowsingDataResult = {
  ok: boolean;
  cleared: {
    history: boolean;
    downloads: boolean;
    cookies: boolean;
    cache: boolean;
  };
  errors?: { scope: string; message: string }[];
};

export interface BrowserAPI {
  navigate: (url: string, options?: { tabId?: string; transition?: string }) => void;
  back: (options?: { tabId?: string }) => void;
  forward: (options?: { tabId?: string }) => void;
  goBack: (options?: { tabId?: string }) => void;
  goForward: (options?: { tabId?: string }) => void;
  reload: (options?: { tabId?: string; ignoreCache?: boolean }) => void;
  createTab: (url?: string, options?: { incognito?: boolean }) => Promise<BrowserNavState>;
  closeTab: (tabId: string) => Promise<{ ok: boolean }>;
  setActiveTab: (tabId: string) => void;
  setBounds: (bounds: { x: number; y: number; width: number; height: number }) => void;
  onState: (handler: (state: BrowserNavState) => void) => (() => void) | void;
  onNavState: (handler: (state: BrowserNavState) => void) => (() => void) | void;
  onTabList: (handler: (summary: BrowserTabList) => void) => (() => void) | void;
  requestTabList: () => Promise<BrowserTabList>;
  onHistoryEntry: (handler: (entry: BrowserHistoryEntry) => void) => (() => void) | void;
  requestHistory: (limit?: number) => Promise<BrowserHistoryEntry[]>;
  onDownload: (handler: (download: BrowserDownloadState) => void) => (() => void) | void;
  requestDownloads: (limit?: number) => Promise<BrowserDownloadState[]>;
  showDownload: (id: string) => Promise<{ ok: boolean; error?: string }>;
  onPermissionPrompt: (handler: (prompt: BrowserPermissionPrompt) => void) => (() => void) | void;
  respondToPermission: (decision: { id: string; decision: "allow" | "deny"; remember?: boolean }) => void;
  onPermissionState: (handler: (state: BrowserPermissionState) => void) => (() => void) | void;
  listPermissions: (origin: string) => Promise<BrowserPermissionState["permissions"]>;
  clearPermission: (origin: string, permission: string) => Promise<{ ok: boolean }>;
  clearOriginPermissions: (origin: string) => Promise<{ ok: boolean }>;
  setPermission: (origin: string, permission: string, setting: "allow" | "deny") => Promise<{ ok: boolean }>;
  clearSiteData: (origin: string) => Promise<{ ok: boolean; error?: string }>;
  clearBrowsingData: (options?: {
    history?: boolean;
    downloads?: boolean;
    cookies?: boolean;
    cache?: boolean;
  }) => Promise<ClearBrowsingDataResult>;
  getSettings: () => Promise<BrowserSettings>;
  getSpellcheckLanguages?: () => Promise<string[]>;
  updateSettings: (patch: Partial<BrowserSettings>) => Promise<BrowserSettings>;
  onSettings: (handler: (settings: BrowserSettings) => void) => (() => void) | void;
  openExternal: (url: string) => Promise<{ ok: boolean; error?: string }>;
  runDiagnostics?: () => Promise<BrowserDiagnosticsResult>;
}

type Unsubscribe = () => void;

declare global {
  interface Window {
    browserAPI?: BrowserAPI;
  }
}

import { isClient } from "@/lib/is-client";

const noop: Unsubscribe = () => undefined;

export function resolveBrowserAPI(): BrowserAPI | undefined {
  if (!isClient()) {
    return undefined;
  }
  const candidate = (window as { browserAPI?: BrowserAPI }).browserAPI;
  if (!candidate || typeof candidate !== "object") {
    return undefined;
  }
  return candidate;
}

export function subscribeNavState(
  api: BrowserAPI | undefined,
  handler: (state: BrowserNavState) => void,
): Unsubscribe {
  if (!api || typeof api.onNavState !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onNavState(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribeTabList(
  api: BrowserAPI | undefined,
  handler: (summary: BrowserTabList) => void,
): Unsubscribe {
  if (!api || typeof api.onTabList !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onTabList(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribeHistory(
  api: BrowserAPI | undefined,
  handler: (entry: BrowserHistoryEntry) => void,
): Unsubscribe {
  if (!api || typeof api.onHistoryEntry !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onHistoryEntry(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribeDownloads(
  api: BrowserAPI | undefined,
  handler: (entry: BrowserDownloadState) => void,
): Unsubscribe {
  if (!api || typeof api.onDownload !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onDownload(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribeSettings(
  api: BrowserAPI | undefined,
  handler: (settings: BrowserSettings) => void,
): Unsubscribe {
  if (!api || typeof api.onSettings !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onSettings(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribePermissionPrompts(
  api: BrowserAPI | undefined,
  handler: (prompt: BrowserPermissionPrompt) => void,
): Unsubscribe {
  if (!api || typeof api.onPermissionPrompt !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onPermissionPrompt(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}

export function subscribePermissionState(
  api: BrowserAPI | undefined,
  handler: (state: BrowserPermissionState) => void,
): Unsubscribe {
  if (!api || typeof api.onPermissionState !== "function" || typeof handler !== "function") {
    return noop;
  }
  const unsubscribe = api.onPermissionState(handler);
  return typeof unsubscribe === "function" ? unsubscribe : noop;
}
