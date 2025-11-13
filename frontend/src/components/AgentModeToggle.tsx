"use client";

import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

type AgentModeToggleProps = {
  enabled: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
};

export function AgentModeToggle({ enabled, disabled = false, onChange }: AgentModeToggleProps) {
  return (
    <label className={cn("inline-flex items-center gap-2 text-xs text-muted-foreground", disabled && "opacity-60")}
    >
      <Switch
        id="agent-mode-toggle"
        checked={enabled}
        disabled={disabled}
        onCheckedChange={onChange}
        className="h-4 w-7"
      />
      <span>Agent mode</span>
    </label>
  );
}

export default AgentModeToggle;
