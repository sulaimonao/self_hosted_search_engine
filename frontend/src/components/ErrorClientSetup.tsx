"use client";

import { useEffect } from "react";
import { sendUiLog } from "@/lib/logging";

export default function ErrorClientSetup() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      try {
        sendUiLog({
          event: "ui.error.window",
          level: "ERROR",
          msg: event.message,
          meta: { filename: event.filename, lineno: event.lineno, colno: event.colno },
        });
      } catch {
        // ignore
      }
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      try {
        const reason = (event.reason && typeof event.reason === 'object') ? JSON.stringify(event.reason) : String(event.reason);
        sendUiLog({
          event: "ui.error.unhandledrejection",
          level: "ERROR",
          msg: reason,
          meta: {},
        });
      } catch {
        // ignore
      }
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection as EventListener);

    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection as EventListener);
    };
  }, []);

  return null;
}
