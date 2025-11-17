"use client";

import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ResearchSession } from "@/lib/researchSession";
import { useResearchSessionLauncher } from "@/hooks/useResearchSessionLauncher";

interface StartResearchSessionDialogProps {
  trigger: ReactNode;
  onStarted?: (session: ResearchSession) => void;
}

export function StartResearchSessionDialog({ trigger, onStarted }: StartResearchSessionDialogProps) {
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const { startSession, isStarting } = useResearchSessionLauncher();

  async function handleStart() {
    try {
      const session = await startSession(topic.trim() || undefined);
      if (session) {
        onStarted?.(session);
      }
      setTopic("");
      setOpen(false);
    } catch {
      // Error handled in hook toast
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (!isStarting ? setOpen(next) : null)}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="bg-app-card text-fg" showCloseButton={!isStarting}>
        <DialogHeader>
          <DialogTitle>Start a research session</DialogTitle>
          <DialogDescription>Give the assistant an optional topic to focus its browsing and note taking.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="session-topic" className="text-xs uppercase tracking-wide text-fg-muted">
            Topic
          </Label>
          <Input
            id="session-topic"
            autoFocus
            placeholder="e.g. AI safety policy updates"
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            disabled={isStarting}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={isStarting}>
            Cancel
          </Button>
          <Button className="bg-accent text-fg-on-accent hover:bg-accent/90" onClick={handleStart} disabled={isStarting}>
            {isStarting ? "Starting…" : "Start session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
