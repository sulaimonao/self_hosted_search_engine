import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export function ThreadSummaryBar() {
  return (
    <div className="mb-3 flex items-center gap-3 rounded-xl border bg-card/60 p-3">
      <Avatar className="size-10 bg-muted">
        <AvatarFallback>AI</AvatarFallback>
      </Avatar>
      <div className="text-sm">
        <p className="font-medium">Research cockpit assistant</p>
        <p className="text-xs text-muted-foreground">Context-aware and linked to current tab</p>
      </div>
    </div>
  );
}
