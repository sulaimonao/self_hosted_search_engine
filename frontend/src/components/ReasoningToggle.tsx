"use client";

import { useEffect } from "react";

import { useUI } from "@/state/ui";

export function ReasoningToggle() {
  const { showReasoning, setShowReasoning, hydrate, hydrated } = useUI();

  useEffect(() => {
    if (!hydrated) {
      hydrate();
    }
  }, [hydrated, hydrate]);

  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
      <input
        type="checkbox"
        className="h-3.5 w-3.5"
        checked={showReasoning}
        onChange={(event) => setShowReasoning(event.target.checked)}
      />
      <span>Show agent steps</span>
    </label>
  );
}

export default ReasoningToggle;
