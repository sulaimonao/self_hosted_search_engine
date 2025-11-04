"use client";

import { useRef } from "react";

import { RenderLoopGuardContextValue, useRenderLoopGuardState } from "@/lib/renderLoopContext";
import { useRenderLoopDiagnostics } from "@/state/useRenderLoopDiagnostics";

function now(): number {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}

function isGuardActive(
  context: RenderLoopGuardContextValue,
  environment: NodeJS.ProcessEnv | undefined,
): boolean {
  if (!context.enabled) {
    return false;
  }
  return (environment?.NODE_ENV ?? process.env.NODE_ENV) === "development";
}

export function useRenderLoopGuard(key: string, max = 30, windowMs = 1000) {
  const context = useRenderLoopGuardState();
  if (!isGuardActive(context, typeof process !== "undefined" ? process.env : undefined)) {
    return;
  }
  if (typeof window === "undefined") {
    return;
  }

  const stampRef = useRef<number>(now());
  const countRef = useRef<number>(0);
  const warnedRef = useRef(false);

  const current = now();
  if (current - stampRef.current > windowMs) {
    stampRef.current = current;
    countRef.current = 0;
    warnedRef.current = false;
  }

  countRef.current += 1;
  if (countRef.current > max && !warnedRef.current) {
    warnedRef.current = true;
    // eslint-disable-next-line no-console
    console.error(`[render-loop] ${key} exceeded ${max} renders/${windowMs}ms`);
    useRenderLoopDiagnostics
      .getState()
      .record({
        key,
        count: countRef.current,
        timestamp: Date.now(),
        windowMs,
      });
  }
}

