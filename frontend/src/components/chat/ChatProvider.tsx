"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

type ChatCtx = {
  open: boolean;
  setOpen: (value: boolean) => void;
  toggle: () => void;
  ready: boolean;
};

const Context = createContext<ChatCtx | null>(null);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [ready, setReady] = useState(false);

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

  const toggle = useCallback(() => setOpen((value) => !value), []);

  return <Context.Provider value={{ open, setOpen, toggle, ready }}>{children}</Context.Provider>;
}

export function useChat() {
  const value = useContext(Context);
  if (!value) {
    throw new Error("useChat must be used within ChatProvider");
  }
  return value;
}
