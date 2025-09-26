<<<<<<< ours
<<<<<<< ours
export function WebPreview() {
  return (
    <div className="flex flex-col h-full bg-muted/20">
      <div className="flex items-center p-2 border-b">
        <input
          type="text"
          placeholder="https://example.com"
          className="flex-1 p-2 border rounded-md"
        />
      </div>
      <div className="flex-1 p-4">
        <p>Web Preview</p>
      </div>
    </div>
  );
}
=======
=======
>>>>>>> theirs
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ExternalLink, Globe, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { isProbablyUrl } from "@/lib/utils";

interface WebPreviewProps {
  url: string;
  onNavigate: (url: string) => void;
  onQueueAction?: (action: "extract" | "summarize" | "crawl", payload: { url: string; text?: string }) => void;
  onDragStart?: (url: string) => void;
}

export function WebPreview({ url, onNavigate, onQueueAction, onDragStart }: WebPreviewProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [input, setInput] = useState(url);
  const [history, setHistory] = useState<string[]>(() => (url ? [url] : []));
  const [index, setIndex] = useState(history.length - 1);
  const [loading, setLoading] = useState(false);
  const [selection, setSelection] = useState<{ text: string; rect: DOMRect | null }>({ text: "", rect: null });
  const [selectionError, setSelectionError] = useState<string | null>(null);

  useEffect(() => {
    setInput(url);
    if (url && history[history.length - 1] !== url) {
      setHistory((prev) => [...prev.slice(0, index + 1), url]);
      setIndex((prev) => prev + 1);
    }
    if (url) {
      setLoading(true);
    }
  }, [url, history, index]);

  const canGoBack = index > 0;
  const canGoForward = index < history.length - 1;

  const handleBack = () => {
    if (!canGoBack) return;
    const nextIndex = index - 1;
    setIndex(nextIndex);
    onNavigate(history[nextIndex]);
  };

  const handleForward = () => {
    if (!canGoForward) return;
    const nextIndex = index + 1;
    setIndex(nextIndex);
    onNavigate(history[nextIndex]);
  };

  const handleRefresh = () => {
    if (!history[index]) return;
    setLoading(true);
    iframeRef.current?.contentWindow?.location?.reload();
  };

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    const loadHandler = () => {
      setLoading(false);
      setSelection({ text: "", rect: null });
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;
        const handleMouseUp = () => {
          try {
            const win = iframe.contentWindow;
            const sel = win?.getSelection?.();
            const text = sel?.toString() ?? "";
            if (text.trim().length > 0) {
              const range = sel?.getRangeAt(0);
              const rect = range ? range.getBoundingClientRect() : null;
              setSelection({ text, rect });
            } else {
              setSelection({ text: "", rect: null });
            }
            setSelectionError(null);
          } catch (error) {
            setSelectionError("Selection unavailable on this page due to browser security restrictions.");
          }
        };
        doc.addEventListener("mouseup", handleMouseUp);
        return () => {
          doc.removeEventListener("mouseup", handleMouseUp);
        };
      } catch (error) {
        setSelectionError("Selection unavailable on this page due to browser security restrictions.");
      }
    };

    iframe.addEventListener("load", loadHandler);

    return () => {
      iframe.removeEventListener("load", loadHandler);
    };
  }, []);

  const selectionActions = useMemo(() => {
    if (!selection.text) return [] as const;
    return [
      {
        label: "Extract",
        action: "extract" as const,
      },
      {
        label: "Summarize",
        action: "summarize" as const,
      },
      {
        label: "Queue crawl",
        action: "crawl" as const,
      },
    ];
  }, [selection.text]);

  return (
    <Card className="flex h-full flex-col border-muted-foreground/30">
      <CardHeader className="border-b border-border/60 pb-3">
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const value = input.trim();
            if (!value) return;
            const nextUrl = isProbablyUrl(value) ? value : `https://duckduckgo.com/?q=${encodeURIComponent(value)}`;
            onNavigate(nextUrl);
          }}
        >
          <div className="flex items-center gap-2">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button type="button" variant="ghost" size="icon" onClick={handleBack} disabled={!canGoBack}>
                    <ArrowLeft className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Back</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button type="button" variant="ghost" size="icon" onClick={handleForward} disabled={!canGoForward}>
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Forward</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button type="button" variant="ghost" size="icon" onClick={handleRefresh}>
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Reload</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Paste a URL or search query"
            className="flex-1"
            onDragStart={(event) => {
              if (isProbablyUrl(input)) {
                event.dataTransfer.setData("text/uri-list", input);
                onDragStart?.(input);
              }
            }}
          />
          <Button type="submit" className="flex items-center gap-2">
            <Globe className="h-4 w-4" />
            Go
          </Button>
          {url && (
            <Button type="button" variant="ghost" size="icon" onClick={() => window.open(url, "_blank") ?? undefined}>
              <ExternalLink className="h-4 w-4" />
            </Button>
          )}
        </form>
      </CardHeader>
      <CardContent className="relative flex flex-1 overflow-hidden p-0">
        {url ? (
          <iframe ref={iframeRef} src={url} className="size-full" title="Web preview" />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
            Load a page to begin.
          </div>
        )}
        {selection.text && selection.rect && (
          <div
            className="pointer-events-auto fixed z-30 flex flex-col gap-2 rounded-xl border border-border bg-background/95 p-3 shadow-lg"
            style={{
              top:
                typeof window !== "undefined"
                  ? Math.max(selection.rect.top + window.scrollY - 120, 16)
                  : 16,
              left:
                typeof window !== "undefined"
                  ? Math.min(selection.rect.left + window.scrollX, window.innerWidth - 220)
                  : 16,
            }}
          >
            <p className="max-w-xs text-sm text-muted-foreground">{selection.text.slice(0, 240)}</p>
            <div className="flex flex-wrap gap-2">
              {selectionActions.map((action) => (
                <Button
                  key={action.label}
                  variant="secondary"
                  size="sm"
                  onClick={() => onQueueAction?.(action.action, { url, text: selection.text })}
                >
                  {action.label}
                </Button>
              ))}
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSelection({ text: "", rect: null })}>
              Dismiss
            </Button>
          </div>
        )}
        {selectionError && (
          <div className="pointer-events-none absolute bottom-4 right-4 max-w-sm rounded-md border border-dashed border-border bg-background/90 p-3 text-xs text-muted-foreground shadow">
            {selectionError}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
