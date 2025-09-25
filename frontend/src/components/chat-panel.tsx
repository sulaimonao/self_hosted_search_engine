import { AgentLog } from "./agent-log";

export function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-background">
      <div className="flex-1 p-4 overflow-y-auto">
        <p>Chat Panel</p>
      </div>
      <AgentLog />
    </div>
  );
}