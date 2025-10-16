"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { CopilotEvent } from "@/lib/events";
import { resolveBrowserAPI, type BrowserNavError, type BrowserTabList } from "@/lib/browser-ipc";
import { setIfChanged, wrapSetStateDebug } from "@/lib/store/utils";

export type Panel = "localSearch" | "collections" | "chat" | "shadow" | "agentLog";

type Tab = {
  id: string;
  title: string;
  url: string;
  favicon?: string | null;
  canGoBack: boolean;
  canGoForward: boolean;
  isLoading?: boolean;
  error?: BrowserNavError | null;
};

type Notification = {
  key: string;
  latest: number;
  kind: CopilotEvent["kind"];
  site?: string;
  count: number;
  lastMessage?: string;
  muted?: boolean;
  progress?: number;
};

export type HealthSnapshot = {
  status: "ok" | "degraded" | "error";
  raw?: unknown;
  checkedAt: number;
};

type BrowserState = {
  desiredUrl?: string | null;
};

type AppState = {
  tabs: Tab[];
  activeTabId?: string;
  mode: "browser" | "research";
  shadowEnabled: boolean;

  notifications: Record<string, Notification>;
  panelOpen?: Panel;
  health: HealthSnapshot | null;
  browser: BrowserState;

  activeTab?: () => Tab | undefined;

  addTab: (url: string, title?: string) => string;
  updateTab: (id: string, patch: Partial<Tab>) => void;
  closeTab: (id: string) => void;
  setActive: (id: string) => void;
  replaceTabs: (summary: BrowserTabList) => void;
  setMode: (mode: AppState["mode"]) => void;
  setShadow: (enabled: boolean) => void;
  openPanel: (panel?: Panel) => void;

  setHealth: (snapshot: HealthSnapshot | null) => void;
  setBrowserDesiredUrl: (url?: string | null) => void;

  pushEvent: (event: CopilotEvent) => void;
  clearNotifications: () => void;
  muteNotification: (key: string, muted: boolean) => void;
};

function createId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function comparePayload(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) {
    return true;
  }
  if (!a || !b) {
    return false;
  }
  if (typeof a !== "object" || typeof b !== "object") {
    return false;
  }
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

function notificationsEqual(previous: Notification | undefined, next: Notification): boolean {
  if (!previous) {
    return false;
  }
  return (
    previous.latest === next.latest &&
    previous.count === next.count &&
    previous.lastMessage === next.lastMessage &&
    previous.kind === next.kind &&
    previous.site === next.site &&
    previous.muted === next.muted &&
    previous.progress === next.progress
  );
}

const DEFAULT_TAB_TITLE = "Welcome";

const DEFAULT_TAB: Tab = {
  id: "default",
  title: DEFAULT_TAB_TITLE,
  url: "https://wikipedia.org",
  favicon: null,
  canGoBack: false,
  canGoForward: false,
  isLoading: false,
  error: null,
};

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => {
      const guardedSet = setIfChanged<AppState>(set, get);
      return {
        tabs: [DEFAULT_TAB],
        activeTabId: DEFAULT_TAB.id,
        mode: "browser",
        shadowEnabled: false,
        notifications: {},
        health: null,
        browser: {
          desiredUrl: DEFAULT_TAB.url,
        },

        activeTab: () => {
          const state = get();
          const targetId = state.activeTabId ?? state.tabs[0]?.id;
          return state.tabs.find((tab) => tab.id === targetId);
        },

        addTab: (url, title) => {
          const api = resolveBrowserAPI();
          if (api) {
            void api
              .createTab(url)
              .catch((error) => console.warn("[browser] failed to create tab", error));
            return url;
          }
          const id = createId();
          const next: Tab = {
            id,
            title: title ?? url,
            url,
            favicon: null,
            canGoBack: false,
            canGoForward: false,
            isLoading: false,
            error: null,
          };
          guardedSet((state) => ({
            tabs: [...state.tabs, next],
            activeTabId: id,
            browser: {
              ...state.browser,
              desiredUrl: next.url,
            },
          }));
          return id;
        },

        updateTab: (id, patch) =>
          guardedSet((state) => {
            let tabsChanged = false;
            let desiredUrl = state.browser.desiredUrl ?? null;

            const nextTabs = state.tabs.map((tab) => {
              if (tab.id !== id) {
                return tab;
              }
              let changed = false;
              const nextTab = { ...tab };
              for (const [key, value] of Object.entries(patch) as [keyof Tab, Tab[keyof Tab]][]) {
                if (!Object.is(nextTab[key], value)) {
                  nextTab[key] = value;
                  changed = true;
                }
              }
              if (changed && (state.activeTabId ?? state.tabs[0]?.id) === id && typeof nextTab.url === "string") {
                desiredUrl = nextTab.url;
              }
              tabsChanged ||= changed;
              return changed ? nextTab : tab;
            });

            const patchState: Partial<AppState> = {};
            if (tabsChanged) {
              patchState.tabs = nextTabs;
            }
            if (desiredUrl !== (state.browser.desiredUrl ?? null)) {
              patchState.browser = { ...state.browser, desiredUrl };
            }
            return patchState;
          }),

        closeTab: (id) => {
          const api = resolveBrowserAPI();
          if (api) {
            void api.closeTab(id).catch((error) => console.warn("[browser] failed to close tab", error));
            return;
          }
          guardedSet((state) => {
            if (state.tabs.length <= 1) {
              return {};
            }
            const currentIndex = state.tabs.findIndex((tab) => tab.id === id);
            if (currentIndex < 0) {
              return {};
            }
            const nextTabs = state.tabs.filter((tab) => tab.id !== id);
            const nextActive =
              state.activeTabId === id
                ? nextTabs[Math.max(0, currentIndex - 1)]?.id ?? nextTabs[0]?.id
                : state.activeTabId;
            const patch: Partial<AppState> = {
              tabs: nextTabs,
              activeTabId: nextActive,
            };
            if (nextActive) {
              const activeTab = nextTabs.find((tab) => tab.id === nextActive);
              if (activeTab?.url && activeTab.url !== state.browser.desiredUrl) {
                patch.browser = { ...state.browser, desiredUrl: activeTab.url };
              }
            }
            return patch;
          });
        },

        setActive: (id) => {
          const api = resolveBrowserAPI();
          if (api) {
            api.setActiveTab(id);
          }
          guardedSet((state) => {
            if (state.activeTabId === id) {
              return {};
            }
            const nextActive = id ?? state.tabs[0]?.id;
            const patch: Partial<AppState> = { activeTabId: nextActive };
            const activeTab = state.tabs.find((tab) => tab.id === nextActive);
            if (activeTab?.url && activeTab.url !== state.browser.desiredUrl) {
              patch.browser = { ...state.browser, desiredUrl: activeTab.url };
            }
            return patch;
          });
        },

        replaceTabs: (summary) =>
          guardedSet((state) => {
            if (!summary || !Array.isArray(summary.tabs)) {
              return {};
            }
            const mapped: Tab[] = summary.tabs.map((tab) => ({
              id: tab.tabId,
              title: tab.title ?? tab.url ?? DEFAULT_TAB_TITLE,
              url: tab.url,
              favicon: tab.favicon ?? null,
              canGoBack: tab.canGoBack,
              canGoForward: tab.canGoForward,
              isLoading: Boolean(tab.isLoading),
              error: tab.error ?? null,
            }));
            if (!mapped.length) {
              return {};
            }
            const tabsChanged =
              mapped.length !== state.tabs.length ||
              mapped.some((tab, index) => {
                const existing = state.tabs[index];
                if (!existing) return true;
                return (
                  existing.id !== tab.id ||
                  existing.url !== tab.url ||
                  existing.title !== tab.title ||
                  existing.favicon !== tab.favicon ||
                  existing.canGoBack !== tab.canGoBack ||
                  existing.canGoForward !== tab.canGoForward ||
                  existing.isLoading !== tab.isLoading ||
                  (existing.error?.description ?? null) !== (tab.error?.description ?? null) ||
                  (existing.error?.code ?? null) !== (tab.error?.code ?? null)
                );
              });

            const desiredActive = summary.activeTabId;
            const nextActive =
              mapped.find((tab) => tab.id === desiredActive)?.id ??
              mapped[0]?.id ??
              state.activeTabId;
            const patch: Partial<AppState> = {};
            if (tabsChanged) {
              patch.tabs = mapped;
            }
            if (nextActive !== state.activeTabId) {
              patch.activeTabId = nextActive;
            }
            const nextUrl = mapped.find((tab) => tab.id === nextActive)?.url;
            if (nextUrl && nextUrl !== state.browser.desiredUrl) {
              patch.browser = { ...state.browser, desiredUrl: nextUrl };
            }
            return patch;
          }),
        setMode: (mode) =>
          guardedSet((state) => {
            if (state.mode === mode) {
              return {};
            }
            return { mode };
          }),
        setShadow: (enabled) =>
          guardedSet((state) => {
            if (state.shadowEnabled === enabled) {
              return {};
            }
            return { shadowEnabled: enabled };
          }),
        openPanel: (panel) =>
          guardedSet((state) => {
            if (state.panelOpen === panel) {
              return {};
            }
            return { panelOpen: panel };
          }),

        setHealth: (snapshot) =>
          guardedSet((state) => {
            const current = state.health;
            if (
              (current === null && snapshot === null) ||
              (current &&
                snapshot &&
                current.status === snapshot.status &&
                current.checkedAt === snapshot.checkedAt &&
                comparePayload(current.raw, snapshot.raw))
            ) {
              return {};
            }
            return { health: snapshot };
          }),

        setBrowserDesiredUrl: (url) =>
          guardedSet((state) => {
            const existing = state.browser.desiredUrl ?? null;
            const next = url ?? null;
            if (existing === next) {
              return {};
            }
            return { browser: { ...state.browser, desiredUrl: next } };
          }),

        pushEvent: (event) =>
          guardedSet((state) => {
            const key = `${event.kind}:${event.site ?? ""}`;
            const previous = state.notifications[key];
            const next: Notification = {
              key,
              kind: event.kind,
              site: event.site,
              count: (previous?.count ?? 0) + (event.count ?? 1),
              latest: event.ts,
              lastMessage: event.message ?? previous?.lastMessage,
              muted: previous?.muted ?? false,
              progress: event.progress ?? previous?.progress,
            };
            if (notificationsEqual(previous, next)) {
              return {};
            }
            return { notifications: { ...state.notifications, [key]: next } };
          }),

        clearNotifications: () =>
          guardedSet((state) => {
            if (!Object.keys(state.notifications).length) {
              return {};
            }
            return { notifications: {} };
          }),
        muteNotification: (key, muted) =>
          guardedSet((state) => {
            const current = state.notifications[key];
            if (!current || current.muted === muted) {
              return {};
            }
            return {
              notifications: {
                ...state.notifications,
                [key]: { ...current, muted },
              },
            };
          }),
      };
    },
    {
      name: "copilot-browser-state",
      partialize: (state) => ({
        tabs: state.tabs,
        activeTabId: state.activeTabId,
        mode: state.mode,
        shadowEnabled: state.shadowEnabled,
      }),
    },
  ),
);

wrapSetStateDebug(useAppStore);
