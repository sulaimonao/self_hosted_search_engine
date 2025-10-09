"use client";

import { useCallback } from "react";

export interface ToastPayload {
  title?: string;
  description?: string;
  variant?: "default" | "destructive" | "warning";
}

export function useToast() {
  const toast = useCallback((payload: ToastPayload) => {
    const { title, description, variant = "default" } = payload ?? {};
    const summary = [title, description].filter(Boolean).join(" – ") || "Toast";
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.log(`[toast:${variant}]`, summary);
    }
  }, []);

  return { toast };
}
