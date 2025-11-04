"use client";

import { useCallback, useMemo, useRef, useState } from "react";

type Updater<T> = T | ((prev: T) => T);

function resolveNext<T>(next: Updater<T>, prev: T): T {
  return typeof next === "function" ? (next as (prev: T) => T)(prev) : next;
}

/** setState that only commits when next !== prev (Object.is) */
export function useSafeState<T>(initial: T | (() => T)) {
  const [state, setState] = useState<T>(() =>
    typeof initial === "function" ? (initial as () => T)() : initial,
  );

  const stableSet = useCallback((next: Updater<T>) => {
    setState((prev) => {
      const computed = resolveNext(next, prev);
      return Object.is(prev, computed) ? prev : computed;
    });
  }, []);

  return [state, stableSet] as const;
}

function shallowEqual(a: unknown, b: unknown): boolean {
  if (Object.is(a, b)) {
    return true;
  }
  if (typeof a !== "object" || typeof b !== "object" || !a || !b) {
    return false;
  }
  const aKeys = Object.keys(a as Record<string, unknown>);
  const bKeys = Object.keys(b as Record<string, unknown>);
  if (aKeys.length !== bKeys.length) {
    return false;
  }
  for (const key of aKeys) {
    if (!Object.prototype.hasOwnProperty.call(b, key)) {
      return false;
    }
    if (!Object.is(
      (a as Record<string, unknown>)[key],
      (b as Record<string, unknown>)[key],
    )) {
      return false;
    }
  }
  return true;
}

/** stable memo that re-computes only when shallowly different */
export function useStableMemo<T extends object>(factory: () => T, deps: ReadonlyArray<unknown>) {
  const ref = useRef<T | null>(null);
  return useMemo(() => {
    const value = factory();
    if (ref.current && shallowEqual(ref.current, value)) {
      return ref.current;
    }
    ref.current = value;
    return value;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/** event pattern to avoid putting changing callbacks into deps */
export function useEvent<T extends (...args: unknown[]) => unknown>(fn: T) {
  const ref = useRef(fn);
  ref.current = fn;
  return useCallback((...args: Parameters<T>): ReturnType<T> => ref.current(...args), []);
}

