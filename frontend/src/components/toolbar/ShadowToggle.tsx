"use client";

import { useCallback } from "react";
import { Glasses, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ShadowToggleProps {
  enabled: boolean;
  disabled?: boolean;
  loading?: boolean;
  onToggle: (next: boolean) => void | Promise<void>;
  label?: string;
  error?: string | null;
}

export function ShadowToggle({
  enabled,
  disabled = false,
  loading = false,
  onToggle,
  label = "Toggle shadow mode",
  error = null,
}: ShadowToggleProps) {
  const handleClick = useCallback(() => {
    if (disabled || loading) {
      return;
    }
    void onToggle(!enabled);
  }, [disabled, loading, enabled, onToggle]);

  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        size="sm"
        variant={enabled ? "default" : "outline"}
        onClick={handleClick}
        disabled={disabled || loading}
        aria-pressed={enabled}
        aria-label={label}
      >
        {loading ? (
          <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" aria-hidden />
        ) : (
          <Glasses className="mr-2 h-3.5 w-3.5" aria-hidden />
        )}
        {enabled ? "Shadow on" : "Shadow off"}
      </Button>
      {error ? (
        <span className="text-xs text-destructive" role="status">
          {error}
        </span>
      ) : null}
    </div>
  );
}
