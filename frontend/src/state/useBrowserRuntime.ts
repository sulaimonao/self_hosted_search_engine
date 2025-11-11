"use client";

import { create } from "zustand";

import type {
  BrowserDownloadState,
  BrowserHistoryEntry,
  BrowserPermissionPrompt,
  BrowserPermissionState,
  BrowserSettings,
} from "@/lib/browser-ipc";

const MAX_HISTORY_ENTRIES = 200;
const MAX_DOWNLOADS = 50;

type RuntimeState = {
  history: BrowserHistoryEntry[];
  setHistory: (entries: BrowserHistoryEntry[]) => void;
  addHistory: (entry: BrowserHistoryEntry) => void;

  downloads: Record<string, BrowserDownloadState>;
  downloadOrder: string[];
  upsertDownload: (entry: BrowserDownloadState) => void;
  removeDownload: (id: string) => void;
  clearDownloads: () => void;

  downloadsOpen: boolean;
  setDownloadsOpen: (open: boolean) => void;

  permissionPrompt?: BrowserPermissionPrompt | null;
  setPermissionPrompt: (prompt?: BrowserPermissionPrompt | null) => void;

  permissions: Record<string, BrowserPermissionState["permissions"]>;
  updatePermissions: (state: BrowserPermissionState) => void;

  settings?: BrowserSettings;
  setSettings: (settings: BrowserSettings) => void;
};

export const useBrowserRuntimeStore = create<RuntimeState>((set) => ({
  history: [],
  setHistory: (entries) =>
    set({
      history: entries
        .slice()
        .sort((a, b) => (b.visitTime ?? 0) - (a.visitTime ?? 0))
        .slice(0, MAX_HISTORY_ENTRIES),
    }),
  addHistory: (entry) =>
    set((state) => {
      const existingIndex = state.history.findIndex((item) => item.id === entry.id);
      const nextHistory = existingIndex >= 0 ? [...state.history] : [entry, ...state.history];
      if (existingIndex >= 0) {
        nextHistory[existingIndex] = entry;
      }
      const sorted = nextHistory
        .sort((a, b) => (b.visitTime ?? 0) - (a.visitTime ?? 0))
        .slice(0, MAX_HISTORY_ENTRIES);
      return { history: sorted };
    }),

  downloads: {},
  downloadOrder: [],
  upsertDownload: (entry) =>
    set((state) => {
      if (entry.deleted) {
        if (!state.downloads[entry.id]) {
          return state;
        }
        const nextDownloads = { ...state.downloads };
        delete nextDownloads[entry.id];
        return {
          downloads: nextDownloads,
          downloadOrder: state.downloadOrder.filter((candidate) => candidate !== entry.id),
        };
      }
      const downloads = { ...state.downloads, [entry.id]: entry };
      const order = state.downloadOrder.includes(entry.id)
        ? state.downloadOrder
        : [entry.id, ...state.downloadOrder].slice(0, MAX_DOWNLOADS);
      return { downloads, downloadOrder: order };
    }),
  removeDownload: (id) =>
    set((state) => {
      if (!state.downloads[id]) {
        return state;
      }
      const nextDownloads = { ...state.downloads };
      delete nextDownloads[id];
      return {
        downloads: nextDownloads,
        downloadOrder: state.downloadOrder.filter((candidate) => candidate !== id),
      };
    }),
  clearDownloads: () => set({ downloads: {}, downloadOrder: [] }),

  downloadsOpen: false,
  setDownloadsOpen: (open) => set({ downloadsOpen: open }),

  permissionPrompt: null,
  setPermissionPrompt: (prompt) => set({ permissionPrompt: prompt ?? null }),

  permissions: {},
  updatePermissions: (state) =>
    set((current) => ({
      permissions: { ...current.permissions, [state.origin]: state.permissions },
    })),

  settings: undefined,
  setSettings: (settings) => set({ settings }),
}));
