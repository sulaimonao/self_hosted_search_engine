import { create } from "zustand";

type Mode = "search" | "browser";

interface AppState {
  mode: Mode;
  shadow: boolean;
  setMode: (mode: Mode) => void;
  toggleShadow: () => void;
}

export const useApp = create<AppState>((set) => ({
  mode: "search",
  shadow: false,
  setMode: (mode) => set({ mode }),
  toggleShadow: () =>
    set((state) => ({
      shadow: !state.shadow,
    })),
}));
