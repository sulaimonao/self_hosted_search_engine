"use client";

import { useEffect } from "react";

import { useAgentTrace, useAgentTraceSubscription } from "@/state/agentTrace";
import { useUI } from "@/state/ui";

type AgentTracePanelProps = {
  chatId: string;
  messageId?: string | null;
};

export function AgentTracePanel({ chatId, messageId }: AgentTracePanelProps) {
  const { showReasoning, hydrate, hydrated } = useUI();
  const steps = useAgentTrace(chatId, messageId ?? null);

  useAgentTraceSubscription(chatId, showReasoning);

  useEffect(() => {
    if (!hydrated) {
      hydrate();
    }
  }, [hydrated, hydrate]);

  if (!showReasoning) {
    return null;
  }

  return (
    <div className="mt-3 space-y-2 rounded-md border border-dashed border-border/60 bg-muted/40 p-3 text-xs">
      <p className="font-semibold uppercase tracking-wide text-muted-foreground">Agent steps</p>
      {steps.length === 0 ? (
        <p className="text-muted-foreground">Waiting for tool activity…</p>
      ) : (
        <ul className="space-y-2">
          {steps.map((step, index) => (
            <li key={`${index}:${step.tool ?? "unknown"}`} className="rounded border border-border/70 bg-background/70 p-2 shadow-sm">
              <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-wide text-muted-foreground/80">
                <span>{step.tool ?? "unknown tool"}</span>
                <span>{step.status ?? "pending"}</span>
              </div>
              {step.duration_ms ? (
                <p className="text-[11px] text-muted-foreground">{step.duration_ms.toFixed(0)} ms</p>
              ) : null}
              {step.excerpt ? (
                <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted px-2 py-1 text-[11px] text-muted-foreground">
                  {step.excerpt}
                </pre>
              ) : null}
              <div className="mt-1 flex gap-3 text-[10px] text-muted-foreground/80">
                <span>Input tokens: {step.token_in ?? "–"}</span>
                <span>Output tokens: {step.token_out ?? "–"}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default AgentTracePanel;
