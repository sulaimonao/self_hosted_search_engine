"use client";

import React, { Profiler } from "react";

import { useRenderLoopGuardState } from "@/lib/renderLoopContext";

type Props = {
  children: React.ReactNode;
};

export function DevProfiler({ children }: Props) {
  const { enabled } = useRenderLoopGuardState();
  const shouldProfile = process.env.NODE_ENV === "development" && enabled;

  if (!shouldProfile) {
    return <>{children}</>;
  }

  return (
    <Profiler
      id="root"
      onRender={(_, __, ___, ____, _____, commitCount) => {
        if (commitCount > 50) {
          // eslint-disable-next-line no-console
          console.error("[render-loop] root profiler high commit rate");
        }
      }}
    >
      {children}
    </Profiler>
  );
}

