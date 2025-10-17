"use client";

import { AlertTriangle, Loader2, PlugZap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ModelSelect, type ModelSelectOption } from "@/components/toolbar/ModelSelect";

interface CopilotHeaderProps {
  chatModels: string[];
  modelOptions?: Array<string | ModelSelectOption>;
  selectedModel: string | null;
  onModelChange: (model: string) => void;
  installing?: boolean;
  onInstallModel?: () => void;
  installMessage?: string | null;
  reachable?: boolean;
  statusLabel?: string;
  timeSummary?: {
    serverLocal: string;
    serverUtc: string;
    serverZone: string;
    clientZone: string;
  } | null;
  controlsDisabled?: boolean;
}

export function CopilotHeader({
  chatModels,
  modelOptions,
  selectedModel,
  onModelChange,
  installing = false,
  onInstallModel,
  installMessage,
  reachable = true,
  statusLabel,
  timeSummary,
  controlsDisabled = false,
}: CopilotHeaderProps) {
  const hasModels = chatModels.length > 0;
  const selectOptions =
    modelOptions && modelOptions.length > 0 ? modelOptions : chatModels;
  const disabled = installing || !hasModels || controlsDisabled;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Copilot chat</h2>
          <p className="text-xs text-muted-foreground">
            {statusLabel ?? (installing ? "Installing model" : hasModels ? "Ready" : "No models detected")}
          </p>
          {timeSummary ? (
            <p
              className="text-xs text-muted-foreground/80"
              title={`Server UTC ${timeSummary.serverUtc}`}
            >
              Server: {timeSummary.serverLocal} ({timeSummary.serverZone}) • You: {timeSummary.clientZone}
            </p>
          ) : null}
        </div>
        {hasModels ? (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">Model</span>
            <ModelSelect
              value={selectedModel}
              options={selectOptions}
              onChange={onModelChange}
              disabled={disabled}
              loading={installing}
            />
          </div>
        ) : null}
      </div>
      {!hasModels ? (
        <div
          className={cn(
            "flex items-center justify-between rounded-md border px-3 py-2 text-xs",
            installing ? "border-muted bg-muted/50" : "border-destructive/40 bg-destructive/10 text-destructive",
          )}
        >
          <div className="flex items-center gap-2">
            {installing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
            <div>
              <p className="font-medium">
                {installing ? "Installing chat model…" : "No chat-capable models available"}
              </p>
              <p className="text-muted-foreground/80">
                {installMessage ?? "Click install to pull Gemma3 (fallback gpt-oss)."}
              </p>
            </div>
          </div>
          <Button
            type="button"
            size="sm"
            variant={installing ? "outline" : "default"}
            onClick={onInstallModel}
            disabled={installing || !onInstallModel}
          >
            {installing ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <PlugZap className="mr-2 h-3.5 w-3.5" />}
            Install model
          </Button>
        </div>
      ) : null}
      {hasModels && !reachable ? (
        <div className="flex items-center gap-2 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-xs text-amber-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          Ollama host unreachable. Start Ollama then retry.
        </div>
      ) : null}
    </div>
  );
}
