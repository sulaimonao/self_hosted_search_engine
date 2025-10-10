"use client";

import { useEffect } from "react";

import { connectEvents } from "@/lib/ws";
import { useAppStore } from "@/state/useAppStore";

export function useEvents() {
  const pushEvent = useAppStore((state) => state.pushEvent);

  useEffect(() => {
    const connection = connectEvents(pushEvent);
    return () => {
      connection?.close?.();
    };
  }, [pushEvent]);
}
