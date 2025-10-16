"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Creates an `onOpenChange` handler that only forwards changes when the boolean value actually flips.
 * Prevents Radix Sheet/Dialog components from feeding back into Zustand every render.
 */
export function useStableOnOpenChange(open: boolean, handler: (next: boolean) => void) {
  const lastValueRef = useRef(open);
  const handlerRef = useRef(handler);

  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);

  useEffect(() => {
    lastValueRef.current = open;
  }, [open]);

  return useCallback((next: boolean) => {
    if (lastValueRef.current === next) {
      return;
    }
    lastValueRef.current = next;
    handlerRef.current(next);
  }, []);
}
