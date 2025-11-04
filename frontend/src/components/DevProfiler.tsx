"use client";

import { Profiler, type ProfilerOnRenderCallback, useCallback, useEffect, useRef } from "react";

import { useDevSettingsStore } from "@/state/devSettings";

const WINDOW_MS = 1000;
const THRESHOLD = 50;

type DevProfilerProps = {
  children: React.ReactNode;
};

export function DevProfiler({ children }: DevProfilerProps) {
  const enabled = useDevSettingsStore((state) => state.renderLoopGuard);
  const hydrate = useDevSettingsStore((state) => state.hydrate);
  const hydrated = useDevSettingsStore((state) => state.hydrated);
  const record = useDevSettingsStore((state) => state.recordRenderLoop);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  const windowStartRef = useRef<number>(typeof performance !== "undefined" ? performance.now() : Date.now());
  const commitCountRef = useRef(0);
  const lastEmissionRef = useRef(0);

  const handleRender = useCallback(
    (id: string) => {
      if (!enabled || !hydrated) {
        return;
      }
      const now = typeof performance !== "undefined" ? performance.now() : Date.now();
      if (now - windowStartRef.current > WINDOW_MS) {
        windowStartRef.current = now;
        commitCountRef.current = 0;
      }
      commitCountRef.current += 1;
      if (commitCountRef.current > THRESHOLD) {
        if (now - lastEmissionRef.current > WINDOW_MS / 2) {
          lastEmissionRef.current = now;
          record({ key: id || "root", count: commitCountRef.current, windowMs: WINDOW_MS });
          if (typeof console !== "undefined" && typeof console.error === "function") {
            console.error(`[render-loop] profiler:${id || "root"} ${commitCountRef.current} commits within ${WINDOW_MS}ms`);
          }
        }
        commitCountRef.current = 0;
        windowStartRef.current = now;
      }
    },
    [enabled, hydrated, record],
  );

  const shouldWrap = process.env.NODE_ENV === "development" && hydrated && enabled;

  const profilerCallback = useCallback<ProfilerOnRenderCallback>(
    (id) => {
      handleRender(id);
    },
    [handleRender],
  );

  if (!shouldWrap) {
    return <>{children}</>;
  }

  return (
    <Profiler id="root" onRender={profilerCallback}>
      {children}
    </Profiler>
  );
}
