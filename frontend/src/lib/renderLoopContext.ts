"use client";

import { createContext, useContext } from "react";

export type RenderLoopGuardContextValue = {
  enabled: boolean;
};

const defaultValue: RenderLoopGuardContextValue = { enabled: false };

export const RenderLoopGuardContext = createContext<RenderLoopGuardContextValue>(defaultValue);

export function useRenderLoopGuardState(): RenderLoopGuardContextValue {
  return useContext(RenderLoopGuardContext);
}

