"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { CopilotEvent } from "@/lib/events";

export type Panel = "localSearch" | "collections" | "chat" | "shadow" | "agentLog";

type Tab = { id: string; title: string; url: string }; // minimal tab state, extend as needed

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

type AppState = {
  tabs: Tab[];
  activeTabId?: string;
  mode: "browser" | "research";
  shadowEnabled: boolean;

  notifications: Record<string, Notification>;
  panelOpen?: Panel;

  activeTab?: () => Tab | undefined;

  addTab: (url: string, title?: string) => string;
  updateTab: (id: string, patch: Partial<Tab>) => void;
  closeTab: (id: string) => void;
  setActive: (id: string) => void;
  setMode: (mode: AppState["mode"]) => void;
  setShadow: (enabled: boolean) => void;
  openPanel: (panel?: Panel) => void;

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

const DEFAULT_TAB: Tab = {
  id: "default",
  title: "Welcome",
  url: "https://wikipedia.org",
};

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      tabs: [DEFAULT_TAB],
      activeTabId: DEFAULT_TAB.id,
      mode: "browser",
      shadowEnabled: false,
      notifications: {},

      activeTab: () => {
        const state = get();
        const targetId = state.activeTabId ?? state.tabs[0]?.id;
        return state.tabs.find((tab) => tab.id === targetId);
      },

      addTab: (url, title) => {
        const id = createId();
        const next: Tab = { id, title: title ?? url, url };
        set((state) => ({
          tabs: [...state.tabs, next],
          activeTabId: id,
        }));
        return id;
      },

      updateTab: (id, patch) =>
        set((state) => ({
          tabs: state.tabs.map((tab) => (tab.id === id ? { ...tab, ...patch } : tab)),
        })),

      closeTab: (id) =>
        set((state) => {
          if (state.tabs.length <= 1) {
            return state;
          }
          const currentIndex = state.tabs.findIndex((tab) => tab.id === id);
          const nextTabs = state.tabs.filter((tab) => tab.id !== id);
          const nextActive =
            state.activeTabId === id
              ? nextTabs[Math.max(0, currentIndex - 1)]?.id ?? nextTabs[0]?.id
              : state.activeTabId;
          return {
            tabs: nextTabs,
            activeTabId: nextActive,
          };
        }),

      setActive: (id) => set({ activeTabId: id }),
      setMode: (mode) => set({ mode }),
      setShadow: (enabled) => set({ shadowEnabled: enabled }),
      openPanel: (panel) => set({ panelOpen: panel }),

      pushEvent: (event) =>
        set((state) => {
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
          return { notifications: { ...state.notifications, [key]: next } };
        }),

      clearNotifications: () => set({ notifications: {} }),
      muteNotification: (key, muted) =>
        set((state) => ({
          notifications: {
            ...state.notifications,
            [key]: { ...state.notifications[key], muted },
          },
        })),
    }),
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
