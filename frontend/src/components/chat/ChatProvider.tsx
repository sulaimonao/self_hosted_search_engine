"use client";
import { createContext, useCallback, useContext, useEffect, useMemo } from "react";

import { useSafeState } from "@/lib/react-safe";

type ChatCtx = {
  open: boolean;
  setOpen: (value: boolean) => void;
  toggle: () => void;
  ready: boolean;
};

const Context = createContext<ChatCtx | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useSafeState(false);
  const [ready, setReady] = useSafeState(false);

  useEffect(() => {
    let active = true;
    if (process.env.NODE_ENV === "test") {
      setReady(true);
      return () => {
        active = false;
      };
    }
    fetch("/api/llm/llm_models")
      .then((response) => {
        if (!response.ok) {
          throw new Error("llm_models probe failed");
        }
        return response.json();
      })
      .then((payload) => {
        if (!active) {
          return;
        }
        const models = Array.isArray(payload?.models) ? payload.models : [];
        const hasModels = models.length > 0 || payload?.models === undefined;
        setReady(hasModels);
      })
      .catch(() => {
        if (active) {
          setReady(false);
        }
      });
    return () => {
      active = false;
    };
  }, [setReady]);

  const toggle = useCallback(() => setOpen((value) => !value), [setOpen]);

  const contextValue = useMemo(() => ({ open, setOpen, toggle, ready }), [open, ready, setOpen, toggle]);

  return <Context.Provider value={contextValue}>{children}</Context.Provider>;
}

export function useChat() {
  const value = useContext(Context);
  if (!value) {
    throw new Error("useChat must be used within ChatProvider");
  }
  return value;
}
