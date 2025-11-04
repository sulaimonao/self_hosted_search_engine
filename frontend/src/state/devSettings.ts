"use client";

import { create } from "zustand";

type RenderLoopEvent = {
  id: string;
  key: string;
  count: number;
  windowMs: number;
  timestamp: number;
};

type DevSettingsState = {
  renderLoopGuard: boolean;
  hydrated: boolean;
  events: RenderLoopEvent[];
  hydrate: () => void;
  setRenderLoopGuard: (value: boolean) => void;
  recordRenderLoop: (event: { key: string; count: number; windowMs: number }) => void;
  clearRenderLoopEvents: () => void;
};

const STORAGE_KEY = "devSettings.renderLoopGuard";
const DEFAULT_ENABLED = process.env.NODE_ENV === "development";

function generateId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const useDevSettingsStore = create<DevSettingsState>((set, get) => ({
  renderLoopGuard: DEFAULT_ENABLED,
  hydrated: false,
  events: [],
  hydrate: () => {
    if (typeof window === "undefined" || get().hydrated) {
      return;
    }
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored !== null) {
        set({ renderLoopGuard: stored === "true", hydrated: true });
        return;
      }
    } catch {
      // ignore storage errors
    }
    set({ hydrated: true });
  },
  setRenderLoopGuard: (value) => {
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(STORAGE_KEY, value ? "true" : "false");
      } catch {
        // ignore storage errors
      }
    }
    set({ renderLoopGuard: value, hydrated: true });
  },
  recordRenderLoop: (event) => {
    const entry: RenderLoopEvent = {
      id: generateId(),
      key: event.key,
      count: event.count,
      windowMs: event.windowMs,
      timestamp: Date.now(),
    };
    set((state) => ({
      events: [entry, ...state.events].slice(0, 12),
    }));
  },
  clearRenderLoopEvents: () => set({ events: [] }),
}));

export type { RenderLoopEvent };
