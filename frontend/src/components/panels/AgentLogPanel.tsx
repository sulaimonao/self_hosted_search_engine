"use client";

export function AgentLogPanel() {
  return (
    <div className="flex h-full w-[22rem] flex-col gap-3 p-4 text-sm">
      <h3 className="text-sm font-semibold">Agent log</h3>
      <div className="flex-1 overflow-y-auto rounded border p-3 text-xs text-muted-foreground">
        Streaming log output appears here.
      </div>
    </div>
  );
}
