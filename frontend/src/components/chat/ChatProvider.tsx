"use client";
import { createContext, useContext, useEffect } from "react";

import { useEvent, useSafeState, useStableMemo } from "@/lib/react-safe";

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
  }, []);

  const toggle = useEvent(() => setOpen((value) => !value));

  const value = useStableMemo(
    () => ({
      open,
      setOpen,
      toggle,
      ready,
    }),
    [open, ready, toggle],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useChat() {
  const value = useContext(Context);
  if (!value) {
    throw new Error("useChat must be used within ChatProvider");
  }
  return value;
}
