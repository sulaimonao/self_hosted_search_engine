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
};

export type BrowserTabList = {
  tabs: BrowserNavState[];
  activeTabId: string | null;
};

export interface BrowserAPI {
  navigate: (url: string, options?: { tabId?: string }) => void;
  goBack: (options?: { tabId?: string }) => void;
  goForward: (options?: { tabId?: string }) => void;
  reload: (options?: { tabId?: string; ignoreCache?: boolean }) => void;
  createTab: (url?: string) => Promise<BrowserNavState>;
  closeTab: (tabId: string) => Promise<{ ok: boolean }>;
  setActiveTab: (tabId: string) => void;
  setBounds: (bounds: { x: number; y: number; width: number; height: number }) => void;
  onNavState: (handler: (state: BrowserNavState) => void) => (() => void) | void;
  onTabList: (handler: (summary: BrowserTabList) => void) => (() => void) | void;
  requestTabList: () => Promise<BrowserTabList>;
}

type Unsubscribe = () => void;

declare global {
  interface Window {
    browserAPI?: BrowserAPI;
  }
}

const noop: Unsubscribe = () => undefined;

export function resolveBrowserAPI(): BrowserAPI | undefined {
  if (typeof window === "undefined") {
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
