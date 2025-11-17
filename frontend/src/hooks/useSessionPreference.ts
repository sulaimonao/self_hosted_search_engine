"use client";

import { useCallback, useEffect, useState } from "react";

import { safeSessionStorage } from "@/utils/isomorphicStorage";

export function useSessionPreference<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(initialValue);

  useEffect(() => {
    const stored = safeSessionStorage.get(key);
    if (stored == null) return;
    try {
      setValue(JSON.parse(stored));
    } catch {
      setValue(stored as T);
    }
  }, [key]);

  const setPreference = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === "function" ? (next as (prev: T) => T)(prev) : next;
        safeSessionStorage.set(key, JSON.stringify(resolved));
        return resolved;
      });
    },
    [key],
  );

  return [value, setPreference] as const;
}
