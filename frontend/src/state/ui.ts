"use client";

import { create } from "zustand";
import { isClient } from "@/lib/is-client";
import { safeLocalStorage } from "@/utils/isomorphicStorage";

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
    const stored = safeLocalStorage.get(STORAGE_KEY);
    set({ showReasoning: stored === "true", hydrated: true });
  },
  setShowReasoning: (value: boolean) => {
    if (isClient()) {
      safeLocalStorage.set(STORAGE_KEY, value ? "true" : "false");
    }
    set({ showReasoning: value });
  },
}));

export function useUI() {
  return useUIStore();
}
