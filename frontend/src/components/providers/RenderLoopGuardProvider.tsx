"use client";

import { useMemo } from "react";
import useSWR from "swr";

import { DevProfiler } from "@/components/DevProfiler";
import type { AppConfig } from "@/lib/configClient";
import { getConfig } from "@/lib/configClient";
import { RenderLoopGuardContext } from "@/lib/renderLoopContext";

type Props = {
  children: React.ReactNode;
};

const DEFAULT_ENABLED = process.env.NODE_ENV !== "production";

export function RenderLoopGuardProvider({ children }: Props) {
  const { data } = useSWR<AppConfig>("runtime-config", getConfig);
  const enabled =
    typeof data?.dev_render_loop_guard === "boolean" ? data.dev_render_loop_guard : DEFAULT_ENABLED;
  const contextValue = useMemo(() => ({ enabled }), [enabled]);

  const shouldProfile = process.env.NODE_ENV === "development" && enabled;
  const content = shouldProfile ? <DevProfiler>{children}</DevProfiler> : children;

  return <RenderLoopGuardContext.Provider value={contextValue}>{content}</RenderLoopGuardContext.Provider>;
}

