"use client";

import { useCallback, useMemo, useRef, useState } from "react";

/** setState that only commits when next !== prev (Object.is) */
export function useSafeState<T>(initial: T) {
  const [state, setState] = useState<T>(initial);
  const guardedSet = useCallback(
    (next: T | ((prev: T) => T)) => {
      setState((prev) => {
        const computed = typeof next === "function" ? (next as (value: T) => T)(prev) : next;
        return Object.is(prev, computed) ? prev : computed;
      });
    },
    [setState],
  );
  return [state, guardedSet] as const;
}

/** stable memo that re-computes only when shallowly different */
export function useStableMemo<T extends Record<string, unknown>>(factory: () => T, deps: ReadonlyArray<unknown>) {
  const previousRef = useRef<T | null>(null);
  const memo = useMemo(() => {
    const next = factory();
    if (previousRef.current && shallowEqual(previousRef.current, next)) {
      return previousRef.current;
    }
    previousRef.current = next;
    return next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return memo;
}

function shallowEqual(a: Record<string, unknown>, b: Record<string, unknown>) {
  if (a === b) {
    return true;
  }
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  for (const key of aKeys) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) {
      return false;
    }
    if (!Object.is(a[key], b[key])) {
      return false;
    }
  }
  return true;
}

/** event pattern to avoid putting changing callbacks into deps */
export function useEvent<T extends (...args: unknown[]) => unknown>(fn: T) {
  const ref = useRef(fn);
  ref.current = fn;
  return useCallback((...args: Parameters<T>): ReturnType<T> => ref.current(...args), []);
}
