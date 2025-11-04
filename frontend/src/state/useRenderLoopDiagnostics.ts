"use client";

import { create } from "zustand";

export type RenderLoopDetection = {
  key: string;
  timestamp: number;
  count: number;
  windowMs: number;
};

type RenderLoopDiagnosticsState = {
  events: RenderLoopDetection[];
  record: (event: RenderLoopDetection) => void;
  clear: () => void;
};

const MAX_EVENTS = 25;

export const useRenderLoopDiagnostics = create<RenderLoopDiagnosticsState>((set) => ({
  events: [],
  record: (event) =>
    set((state) => {
      const next = [...state.events, event];
      if (next.length > MAX_EVENTS) {
        next.splice(0, next.length - MAX_EVENTS);
      }
      return { events: next };
    }),
  clear: () => set({ events: [] }),
}));

