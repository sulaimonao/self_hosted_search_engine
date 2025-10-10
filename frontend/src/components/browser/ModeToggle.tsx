"use client";

import { useCallback } from "react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/state/useAppStore";

export function ModeToggle() {
  const mode = useAppStore((state) => state.mode);
  const setMode = useAppStore((state) => state.setMode);
  const shadowEnabled = useAppStore((state) => state.shadowEnabled);
  const setShadow = useAppStore((state) => state.setShadow);

  const toggleMode = useCallback(() => {
    setMode(mode === "browser" ? "research" : "browser");
  }, [mode, setMode]);

  return (
    <div className="flex items-center gap-3">
      <Button variant="outline" onClick={toggleMode}>
        {mode === "browser" ? "Browser" : "Research"}
      </Button>
      <div className="flex items-center gap-2 text-sm">
        <span>Shadow</span>
        <Switch checked={shadowEnabled} onCheckedChange={setShadow} />
      </div>
    </div>
  );
}
