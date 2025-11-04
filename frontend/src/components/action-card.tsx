"use client";

import { Check, Edit3, ExternalLink, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { ActionStatus, ProposedAction } from "@/lib/types";
import { useSafeNavigate } from "@/lib/useSafeNavigate";

interface ActionCardProps {
  action: ProposedAction;
  onApprove: (action: ProposedAction) => void;
  onEdit: (action: ProposedAction) => void;
  onDismiss: (action: ProposedAction) => void;
}

const STATUS_LABEL: Record<ActionStatus, string> = {
  proposed: "Proposed",
  approved: "Approved",
  dismissed: "Dismissed",
  executing: "Executing",
  done: "Completed",
  error: "Error",
};

export function ActionCard({ action, onApprove, onEdit, onDismiss }: ActionCardProps) {
  const targetUrl = typeof action.metadata?.url === "string" ? action.metadata.url : null;
  const previewText = typeof action.metadata?.preview === "string" ? action.metadata.preview : null;
  const navigate = useSafeNavigate();
  return (
    <Card
      className={cn(
        "border-muted-foreground/20 bg-muted/40 transition",
        action.status === "approved" && "border-primary/70",
        action.status === "dismissed" && "opacity-40",
        action.status === "error" && "border-destructive/60 bg-destructive/10"
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base flex items-center gap-2">
              <span className="capitalize">{action.kind.replace("_", " ")}</span>
              <Badge variant="outline" className="text-[11px]">
                {STATUS_LABEL[action.status]}
              </Badge>
            </CardTitle>
            {action.description && (
              <CardDescription className="pt-1 text-sm text-muted-foreground">
                {action.description}
              </CardDescription>
            )}
          </div>
          {targetUrl && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Open resource"
              onClick={() => {
                if (!targetUrl) return;
                const params = new URLSearchParams({ url: targetUrl });
                navigate.push(`/workspace?${params.toString()}`);
              }}
            >
              <ExternalLink className="h-4 w-4" />
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        {previewText && (
          <p className="text-sm text-muted-foreground mb-3">
            {previewText}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            className="flex items-center gap-1"
            onClick={() => onApprove(action)}
            disabled={action.status === "approved" || action.status === "executing"}
          >
            <Check className="h-4 w-4" /> Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex items-center gap-1"
            onClick={() => onEdit(action)}
          >
            <Edit3 className="h-4 w-4" /> Edit
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="flex items-center gap-1"
            onClick={() => onDismiss(action)}
            disabled={action.status === "dismissed"}
          >
            <Trash2 className="h-4 w-4" /> Dismiss
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
