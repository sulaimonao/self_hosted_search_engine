<<<<<<< ours
<<<<<<< ours
export function ActionCard() {
  return (
    <div className="p-4 border rounded-lg">
      <p>Action Card</p>
      <div className="flex justify-end gap-2 mt-2">
        <button className="px-4 py-2 rounded-md bg-primary text-primary-foreground">Approve</button>
        <button className="px-4 py-2 rounded-md border">Dismiss</button>
      </div>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { AgentAction } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ActionCardProps {
  action: AgentAction;
  onApprove: (action: AgentAction, note?: string) => Promise<void> | void;
  onDismiss: (action: AgentAction) => Promise<void> | void;
  onEdit?: (action: AgentAction, updates: Partial<AgentAction>) => Promise<void> | void;
  compact?: boolean;
}

const statusVariant: Record<AgentAction["status"], "default" | "secondary" | "success" | "warning" | "destructive"> = {
  proposed: "secondary",
  approved: "success",
  dismissed: "destructive",
  running: "warning",
  done: "success",
  error: "destructive",
};

export function ActionCard({ action, onApprove, onDismiss, onEdit, compact }: ActionCardProps) {
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleApprove = async () => {
    try {
      setBusy(true);
      await onApprove(action, note);
      setNote("");
    } finally {
      setBusy(false);
    }
  };

  const handleDismiss = async () => {
    try {
      setBusy(true);
      await onDismiss(action);
    } finally {
      setBusy(false);
    }
  };

  const handleEdit = async () => {
    if (!onEdit) return;
    if (!editing) {
      setEditing(true);
      return;
    }
    try {
      setBusy(true);
      await onEdit(action, { summary: note ? `${action.summary}\n\nNotes: ${note}` : action.summary });
      setEditing(false);
      setNote("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className={cn("border-muted-foreground/20", compact && "shadow-none")}> 
      <CardHeader className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Badge variant={statusVariant[action.status]} className="uppercase tracking-wide">
            {action.type}
          </Badge>
          <Badge variant="outline" className="capitalize">
            {action.status}
          </Badge>
        </div>
        <CardTitle className="text-base font-semibold">{action.title}</CardTitle>
        <CardDescription className="whitespace-pre-line text-sm text-muted-foreground">
          {action.summary}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="rounded-md border border-dashed border-muted-foreground/30 bg-muted/30 p-3">
          <span className="font-medium text-muted-foreground">Payload</span>
          <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
            {JSON.stringify(action.payload, null, 2)}
          </pre>
        </div>
        {(editing || note) && (
          <Textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Add scope notes or overrides before approving"
            className="min-h-[120px]"
          />
        )}
        {!editing && !note && (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)} className="px-2">
            Add notes / edit scope
          </Button>
        )}
      </CardContent>
      <CardFooter className="flex flex-col items-stretch gap-2 sm:flex-row sm:justify-end">
        <Button variant="ghost" disabled={busy} onClick={handleDismiss}>
          Dismiss
        </Button>
        {onEdit && (
          <Button variant="secondary" disabled={busy} onClick={handleEdit}>
            {editing ? "Save" : "Edit"}
          </Button>
        )}
        <Button disabled={busy} onClick={handleApprove}>
          Approve
        </Button>
      </CardFooter>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
