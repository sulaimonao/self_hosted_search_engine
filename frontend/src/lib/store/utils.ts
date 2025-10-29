"use client";

import type { StoreApi, UseBoundStore } from "zustand";

export type StoreSetter<TState extends object> = StoreApi<TState>["setState"];
export type StoreGetter<TState extends object> = StoreApi<TState>["getState"];
export type Comparator = (prev: unknown, next: unknown) => boolean;

const defaultComparator: Comparator = Object.is;

/**
 * Returns a setter that only applies updates when the computed patch actually changes the store.
 * Prevents Zustand feedback loops by skipping redundant writes.
 */
export function setIfChanged<TState extends object>(
  set: StoreSetter<TState>,
  get: StoreGetter<TState>,
  comparator: Comparator = defaultComparator,
) {
  return (update: Partial<TState> | ((state: TState) => Partial<TState>), replace?: boolean): void => {
    const current = get();
    const patch = typeof update === "function" ? (update as (state: TState) => Partial<TState>)(current) : update;

    if (!patch || typeof patch !== "object") {
      return;
    }

    let changed = false;
    const nextPartial: Partial<TState> = {};
    const typedPartial = nextPartial as Record<keyof TState, TState[keyof TState]>;

    for (const key of Object.keys(patch) as Array<keyof TState>) {
      const nextValue = patch[key];
      if (!comparator(current[key], nextValue)) {
        typedPartial[key] = nextValue as TState[keyof TState];
        changed = true;
      }
    }

    if (changed) {
      if (replace) {
        set(nextPartial as TState, true);
      } else {
        set(nextPartial);
      }
    }
  };
}

/**
 * Wraps `setState` in dev so we can log hot call sites that hammer the store.
 */
export function wrapSetStateDebug<TState extends object>(
  store: UseBoundStore<StoreApi<TState>>,
  label = "zustand:setState",
): void {
  if (process.env.NODE_ENV === "production") {
    return;
  }
  if (typeof window === "undefined") {
    return;
  }
  const marker = "__zustandDebugWrapped__";
  if ((store as unknown as Record<string, unknown>)[marker]) {
    return;
  }

  Object.defineProperty(store, marker, {
    value: true,
    enumerable: false,
    writable: false,
  });

  const original = store.setState.bind(store);
  store.setState = ((partial, replace) => {
    if (typeof window !== "undefined") {
      const stack = new Error().stack?.split("\n").slice(1, 6);
      console.debug(`[${label}]`, { partial, replace, stack });
    }
    return original(partial, replace);
  }) as typeof store.setState;
}
