"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { Loader2, RefreshCw, Scissors, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { PageExtractResponse } from "@/lib/types";

interface ContextPanelProps {
  url: string;
  context: PageExtractResponse | null;
  includeContext: boolean;
  onIncludeChange: (value: boolean) => void;
  onExtract: () => void;
  extracting: boolean;
  supportsVision: boolean;
  onManualSubmit: (text: string, title?: string) => void;
  onClear: () => void;
  manualOpenTrigger?: number;
}

export function ContextPanel({
  url,
  context,
  includeContext,
  onIncludeChange,
  onExtract,
  extracting,
  supportsVision,
  onManualSubmit,
  onClear,
  manualOpenTrigger = 0,
}: ContextPanelProps) {
  const [manualOpen, setManualOpen] = useState(false);
  const [manualTitle, setManualTitle] = useState("");
  const [manualText, setManualText] = useState("");

  useEffect(() => {
    if (manualOpenTrigger > 0) {
      setManualOpen(true);
    }
  }, [manualOpenTrigger]);

  const charCount = context?.text?.length ?? 0;
  const previewText = useMemo(() => {
    if (!context?.text) return "";
    return context.text.slice(0, 200).trim();
  }, [context?.text]);

  return (
    <Card className="h-full">
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-sm">Page context</CardTitle>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Switch
              id="context-toggle"
              checked={includeContext}
              onCheckedChange={onIncludeChange}
              disabled={!context}
            />
            <label htmlFor="context-toggle" className="cursor-pointer select-none">
              Attach to next chat
            </label>
          </div>
        </div>
        <p className="truncate text-xs text-muted-foreground" title={url}>
          {url || "No page loaded"}
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 text-xs">
          <Button
            type="button"
            size="sm"
            className="justify-start"
            onClick={onExtract}
            disabled={extracting}
          >
            {extracting ? <Loader2 className="mr-2 h-3 w-3 animate-spin" /> : <RefreshCw className="mr-2 h-3 w-3" />}
            Server extract {supportsVision ? "(text + screenshot)" : "(text)"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={manualOpen ? "default" : "secondary"}
            className="justify-start"
            onClick={() => setManualOpen((value) => !value)}
          >
            <Scissors className="mr-2 h-3 w-3" /> Manual paste
          </Button>
          {context ? (
            <Button type="button" size="sm" variant="ghost" className="justify-start" onClick={onClear}>
              <Trash2 className="mr-2 h-3 w-3" /> Clear context
            </Button>
          ) : null}
        </div>
        {manualOpen ? (
          <div className="space-y-2 rounded-md border bg-muted/40 p-3">
            <Input
              value={manualTitle}
              placeholder="Optional title"
              className="h-8 text-xs"
              onChange={(event) => setManualTitle(event.target.value)}
            />
            <Textarea
              value={manualText}
              rows={6}
              placeholder="Paste relevant text from the page"
              onChange={(event) => setManualText(event.target.value)}
            />
            <div className="flex justify-end gap-2 text-xs">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  setManualTitle("");
                  setManualText("");
                  setManualOpen(false);
                }}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  onManualSubmit(manualText.trim(), manualTitle.trim() || undefined);
                  setManualOpen(false);
                  setManualText("");
                }}
                disabled={!manualText.trim()}
              >
                Save context
              </Button>
            </div>
          </div>
        ) : null}
        {context ? (
          <div className="space-y-3 rounded-md border bg-muted/30 p-3 text-xs">
            <div className="space-y-1">
              <p className="text-sm font-medium text-foreground">{context.title || "Untitled"}</p>
              <p className="text-muted-foreground">
                {charCount.toLocaleString()} characters
                {context.lang ? ` · ${context.lang}` : ""}
              </p>
            </div>
            {previewText ? <p className="whitespace-pre-wrap text-foreground/80">{previewText}…</p> : null}
            {context.screenshot_b64 ? (
              <div className="overflow-hidden rounded border bg-background">
                <Image
                  src={`data:image/png;base64,${context.screenshot_b64}`}
                  alt="Page screenshot"
                  width={320}
                  height={180}
                  className="h-auto w-full"
                />
              </div>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Extract the current page or paste text to provide grounding context for the next chat turn.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
