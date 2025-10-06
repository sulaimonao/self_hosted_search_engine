"use client";

import { useEffect } from "react";
import { cn } from "@/lib/utils";

export interface ToastMessage {
  id: string;
  message: string;
  variant?: "default" | "destructive" | "warning";
  traceId?: string | null;
}

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export function ToastContainer({ toasts, onDismiss }: ToastContainerProps) {
  useEffect(() => {
    const timers = toasts.map((toast) =>
      window.setTimeout(() => onDismiss(toast.id), 6000),
    );
    return () => {
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
    };
  }, [toasts, onDismiss]);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 max-w-full flex-col gap-3">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "pointer-events-auto rounded-md border px-4 py-3 text-sm shadow-md",
            toast.variant === "destructive"
              ? "border-destructive/60 bg-destructive/10 text-destructive"
              : toast.variant === "warning"
                ? "border-amber-500/60 bg-amber-500/10 text-amber-600 dark:text-amber-400"
                : "border-foreground/20 bg-background/95 text-foreground",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="space-y-1">
              <p className="font-medium leading-snug">{toast.message}</p>
              {toast.traceId ? (
                <p className="text-xs text-muted-foreground">trace: {toast.traceId}</p>
              ) : null}
            </div>
            <button
              type="button"
              className="text-xs text-muted-foreground transition hover:text-foreground"
              onClick={() => onDismiss(toast.id)}
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
