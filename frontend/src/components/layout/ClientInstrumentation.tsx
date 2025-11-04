"use client";

import { useEffect } from "react";

import { DevProfiler } from "@/components/DevProfiler";
import { useDevSettingsStore } from "@/state/devSettings";

type ClientInstrumentationProps = {
  children: React.ReactNode;
};

export function ClientInstrumentation({ children }: ClientInstrumentationProps) {
  const hydrate = useDevSettingsStore((state) => state.hydrate);

  useEffect(() => {
    hydrate();
  }, [hydrate]);

  return <DevProfiler>{children}</DevProfiler>;
}
