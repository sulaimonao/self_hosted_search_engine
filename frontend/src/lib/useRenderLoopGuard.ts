"use client";

import { useEffect, useRef } from "react";

import { useDevSettingsStore } from "@/state/devSettings";

const DEFAULT_MAX_COMMITS = 30;
const DEFAULT_WINDOW_MS = 1000;

export function useRenderLoopGuard(key: string, max = DEFAULT_MAX_COMMITS, windowMs = DEFAULT_WINDOW_MS) {
  const enabled = useDevSettingsStore((state) => state.renderLoopGuard);
  const record = useDevSettingsStore((state) => state.recordRenderLoop);
  const hydrate = useDevSettingsStore((state) => state.hydrate);
  const hydrated = useDevSettingsStore((state) => state.hydrated);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const windowStartRef = useRef<number>(
    typeof performance !== "undefined" ? performance.now() : Date.now(),
  );
  const counterRef = useRef(0);
  const lastEmissionRef = useRef(0);

  if (!hydrated) {
    return;
  }

  if (!enabled) {
    counterRef.current = 0;
    return;
  }

  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  if (now - windowStartRef.current > windowMs) {
    windowStartRef.current = now;
    counterRef.current = 0;
  }
  counterRef.current += 1;
  if (counterRef.current > max) {
    if (now - lastEmissionRef.current > windowMs / 2) {
      lastEmissionRef.current = now;
      record({ key, count: counterRef.current, windowMs });
      if (typeof console !== "undefined" && typeof console.error === "function") {
        console.error(`[render-loop] ${key} exceeded ${max} renders/${windowMs}ms`);
      }
    }
    counterRef.current = 0;
    windowStartRef.current = now;
  }
}
