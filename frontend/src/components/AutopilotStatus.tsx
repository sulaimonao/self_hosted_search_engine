"use client";

import { useState } from "react";
import type { Verb } from "@/autopilot/executor";

interface AutopilotStatusProps {
  steps?: Verb[];
  mode?: "browser" | "tools" | "multi";
  reason?: string | null;
  onExecute?: () => void;
  onCancel?: () => void;
}

export function AutopilotStatus({
  steps = [],
  mode = "browser",
  reason,
  onExecute,
  onCancel,
}: AutopilotStatusProps) {
  const [executing, setExecuting] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const totalSteps = steps.length;

  const handleExecute = async () => {
    if (!window.autopilotExecutor || executing) {
      return;
    }

    setExecuting(true);
    setError(null);
    setCurrentStep(0);

    try {
      const result = await window.autopilotExecutor.run(
        { steps },
        {
          onHeadlessError: (err) => {
            console.error("[AutopilotStatus] Headless error:", err);
            setError(err.message);
          },
        }
      );

      if (result.headlessErrors.length > 0) {
        setError(`${result.headlessErrors.length} step(s) failed`);
      }

      onExecute?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Execution failed");
    } finally {
      setExecuting(false);
    }
  };

  const handleCancel = () => {
    setExecuting(false);
    setError(null);
    onCancel?.();
  };

  if (steps.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-xl border border-border-subtle bg-app-card p-4 text-sm text-fg shadow-subtle">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            <span className="font-medium text-fg">Autopilot Mode: {mode}</span>
          </div>
          {reason && (
            <p className="ml-4 text-fg-muted">{reason}</p>
          )}
        </div>
        {!executing && (
          <div className="flex gap-2">
            <button
              onClick={handleExecute}
              className="rounded-md border border-transparent bg-accent px-3 py-1 font-medium text-fg-on-accent transition hover:bg-accent/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Execute
            </button>
            <button
              onClick={handleCancel}
              className="rounded-md border border-border-subtle bg-app-card-subtle px-3 py-1 font-medium text-fg transition hover:bg-app-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-fg-muted">Steps: {totalSteps}</span>
          {executing && (
            <span className="text-fg">
              Executing step {currentStep + 1} of {totalSteps}
            </span>
          )}
        </div>

        {executing && (
          <div className="h-2 w-full rounded-full bg-app-subtle">
            <div
              className="h-2 rounded-full bg-accent transition-all duration-300"
              style={{ width: `${((currentStep + 1) / totalSteps) * 100}%` }}
            />
          </div>
        )}
      </div>

      {steps.length > 0 && !executing && (
        <details className="text-sm text-fg">
          <summary className="cursor-pointer font-medium text-fg-muted transition hover:text-fg">
            View steps ({steps.length})
          </summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {steps.map((step, idx) => (
              <div
                key={idx}
                className="rounded-md border border-border-subtle bg-app-card-subtle px-3 py-2 text-sm text-fg"
              >
                <span className="font-mono text-xs">
                  {idx + 1}. {step.type}
                  {step.type === "navigate" && ` → ${step.url}`}
                  {step.type === "click" && ` on ${step.selector || step.text}`}
                  {step.type === "type" && ` into ${step.selector}`}
                  {step.type === "scroll" && (step.selector ? ` to ${step.selector}` : " to coordinates")}
                  {step.type === "hover" && ` over ${step.selector || step.text}`}
                </span>
              </div>
            ))}
          </div>
        </details>
      )}

      {error && (
        <div className="rounded-md border border-border-strong bg-app-card-subtle p-2 text-sm text-state-danger">
          {error}
        </div>
      )}
    </div>
  );
}
