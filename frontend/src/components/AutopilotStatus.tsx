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
    <div className="border border-blue-200 bg-blue-50 rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse" />
            <span className="font-medium text-blue-900">Autopilot Mode: {mode}</span>
          </div>
          {reason && (
            <p className="text-sm text-blue-700 ml-4">{reason}</p>
          )}
        </div>
        {!executing && (
          <div className="flex gap-2">
            <button
              onClick={handleExecute}
              className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
            >
              Execute
            </button>
            <button
              onClick={handleCancel}
              className="px-3 py-1 text-sm bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-blue-700">Steps: {totalSteps}</span>
          {executing && (
            <span className="text-blue-600">
              Executing step {currentStep + 1} of {totalSteps}
            </span>
          )}
        </div>

        {executing && (
          <div className="w-full bg-blue-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${((currentStep + 1) / totalSteps) * 100}%` }}
            />
          </div>
        )}
      </div>

      {steps.length > 0 && !executing && (
        <details className="text-sm">
          <summary className="cursor-pointer text-blue-700 hover:text-blue-900 font-medium">
            View steps ({steps.length})
          </summary>
          <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
            {steps.map((step, idx) => (
              <div
                key={idx}
                className="px-3 py-2 bg-white rounded border border-blue-100 text-gray-700"
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
        <div className="p-2 bg-red-100 border border-red-300 rounded text-sm text-red-800">
          {error}
        </div>
      )}
    </div>
  );
}
