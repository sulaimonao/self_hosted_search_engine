"use client";

import { create } from "zustand";
import { isClient } from "@/lib/is-client";

const STORAGE_KEY = "ui.showReasoning";

type UIState = {
  showReasoning: boolean;
  hydrated: boolean;
  hydrate: () => void;
  setShowReasoning: (value: boolean) => void;
};

export const useUIStore = create<UIState>((set) => ({
  showReasoning: false,
  hydrated: false,
  hydrate: () => {
    if (!isClient()) {
      return;
    }
    const stored = window.localStorage.getItem(STORAGE_KEY);
    set({ showReasoning: stored === "true", hydrated: true });
  },
  setShowReasoning: (value: boolean) => {
    if (isClient()) {
      window.localStorage.setItem(STORAGE_KEY, value ? "true" : "false");
    }
    set({ showReasoning: value });
  },
}));

export function useUI() {
  return useUIStore();
}
