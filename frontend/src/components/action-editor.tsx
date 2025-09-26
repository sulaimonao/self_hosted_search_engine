"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { CrawlScope, ProposedAction } from "@/lib/types";

interface ActionEditorProps {
  action: ProposedAction | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (action: ProposedAction) => void;
}

const crawlScopes: CrawlScope[] = ["page", "domain", "allowed-list", "custom"];

export function ActionEditor({ action, open, onOpenChange, onSave }: ActionEditorProps) {
  const [working, setWorking] = useState<ProposedAction | null>(action);

  useEffect(() => {
    setWorking(action);
  }, [action]);

  if (!working) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>No action selected</DialogTitle>
            <DialogDescription>Select an action card to modify its parameters.</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    );
  }

  const isCrawl = working.kind === "crawl" || working.kind === "queue";
  const isIndex = working.kind === "index";
  const scopeValue = (working.payload.scope as CrawlScope) || "page";
  const maxPages = Number(working.payload.maxPages ?? 25);
  const maxDepth = Number(working.payload.maxDepth ?? 2);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit action</DialogTitle>
          <DialogDescription>
            Update the parameters before approving. Status: <Badge>{working.status}</Badge>
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <label className="text-sm font-medium">Title</label>
            <Input
              value={working.title}
              onChange={(event) => setWorking({ ...working, title: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Summary</label>
            <Textarea
              value={working.description ?? ""}
              rows={3}
              onChange={(event) =>
                setWorking({ ...working, description: event.target.value || undefined })
              }
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="action-url">
              Target URL
            </label>
            <Input
              id="action-url"
              type="url"
              value={String(working.payload.url ?? "")}
              onChange={(event) =>
                setWorking({ ...working, payload: { ...working.payload, url: event.target.value } })
              }
              placeholder="https://example.com"
            />
          </div>
          {isCrawl && (
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="text-sm font-medium">Scope</label>
                <Select
                  value={scopeValue}
                  onValueChange={(value) =>
                    setWorking({
                      ...working,
                      payload: { ...working.payload, scope: value as CrawlScope },
                    })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select scope" />
                  </SelectTrigger>
                  <SelectContent>
                    {crawlScopes.map((scope) => (
                      <SelectItem key={scope} value={scope}>
                        {scope}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Max pages</label>
                <Input
                  type="number"
                  min={1}
                  max={500}
                  value={maxPages}
                  onChange={(event) =>
                    setWorking({
                      ...working,
                      payload: { ...working.payload, maxPages: Number(event.target.value) },
                    })
                  }
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Depth</label>
                <Input
                  type="number"
                  min={0}
                  max={10}
                  value={maxDepth}
                  onChange={(event) =>
                    setWorking({
                      ...working,
                      payload: { ...working.payload, maxDepth: Number(event.target.value) },
                    })
                  }
                />
              </div>
            </div>
          )}
          {isIndex && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Notes</label>
              <Textarea
                rows={3}
                value={String(working.payload.notes ?? "")}
                onChange={(event) =>
                  setWorking({
                    ...working,
                    payload: { ...working.payload, notes: event.target.value },
                  })
                }
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              if (!working.payload.url) {
                return;
              }
              onSave(working);
              onOpenChange(false);
            }}
          >
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
