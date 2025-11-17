import { Badge } from "@/components/ui/badge";

export function AiPanelHeader() {
  return (
    <div className="mb-2 flex items-center justify-between">
      <div>
        <p className="text-xs uppercase text-muted-foreground">AI Copilot</p>
        <p className="font-semibold">HydraFlow thread</p>
      </div>
      <Badge variant="secondary">Live</Badge>
    </div>
  );
}
