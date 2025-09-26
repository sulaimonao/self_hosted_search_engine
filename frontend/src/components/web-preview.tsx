"use client";

import {
  ArrowLeft,
  ArrowRight,
  ExternalLink,
  Loader2,
  RefreshCcw,
  Sparkles,
} from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { ActionKind, SelectionActionPayload } from "@/lib/types";

const DEFAULT_URL = "https://duckduckgo.com";

function normalizeUrl(input: string) {
  try {
    if (!input.trim()) return DEFAULT_URL;
    const trimmed = input.trim();
    if (/^https?:\/\//i.test(trimmed)) {
      return new URL(trimmed).toString();
    }
    if (/^[\w.-]+\.[a-z]{2,}(\/.*)?$/i.test(trimmed)) {
      return new URL(`https://${trimmed}`).toString();
    }
    return new URL(`https://duckduckgo.com/?q=${encodeURIComponent(trimmed)}`).toString();
  } catch {
    return DEFAULT_URL;
  }
}

interface WebPreviewProps {
  url: string;
  history: string[];
  historyIndex: number;
  isLoading?: boolean;
  reloadKey?: number;
  onNavigate: (url: string, options?: { replace?: boolean }) => void;
  onHistoryBack: () => void;
  onHistoryForward: () => void;
  onReload: () => void;
  onOpenInNewTab?: (url: string) => void;
  onSelectionAction?: (kind: ActionKind, payload: SelectionActionPayload) => void;
}

export function WebPreview({
  url,
  history,
  historyIndex,
  isLoading = false,
  reloadKey,
  onNavigate,
  onHistoryBack,
  onHistoryForward,
  onReload,
  onOpenInNewTab,
  onSelectionAction,
}: WebPreviewProps) {
  const [addressValue, setAddressValue] = useState(url || DEFAULT_URL);
  const [highlightMode, setHighlightMode] = useState(false);
  const [selectionText, setSelectionText] = useState("");
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const highlightPollRef = useRef<number | null>(null);

  useEffect(() => {
    setAddressValue(url);
  }, [url]);

  useEffect(() => {
    if (!highlightMode) {
      setSelectionText("");
      setSelectionError(null);
      if (highlightPollRef.current) {
        window.clearInterval(highlightPollRef.current);
      }
      return;
    }
    highlightPollRef.current = window.setInterval(() => {
      try {
        const frame = frameRef.current;
        const selection = frame?.contentWindow?.getSelection();
        if (!selection) return;
        const text = selection.toString();
        if (text && text.trim().length > 0) {
          setSelectionText(text.trim());
          setSelectionError(null);
        }
      } catch {
        setSelectionError(
          "Selection access blocked by this site. Try copying the text manually."
        );
        setSelectionText("");
      }
    }, 400);
    return () => {
      if (highlightPollRef.current) {
        window.clearInterval(highlightPollRef.current);
      }
    };
  }, [highlightMode]);

  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  const handleSubmit = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const nextUrl = normalizeUrl(addressValue);
      onNavigate(nextUrl);
    },
    [addressValue, onNavigate]
  );

  const handleSelectionAction = useCallback(
    (kind: ActionKind) => {
      if (!onSelectionAction) return;
      const text = selectionText.trim();
      if (!text) {
        setSelectionError("Select text in the preview before choosing an action.");
        return;
      }
      const payload: SelectionActionPayload = {
        selection: text,
        url,
      };
      onSelectionAction(kind, payload);
      setHighlightMode(false);
      setSelectionText("");
    },
    [onSelectionAction, selectionText, url]
  );

  const dragData = useMemo(() => ({
    url,
  }), [url]);

  const handleDragStart = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/uri-list", dragData.url);
      event.dataTransfer.setData("text/plain", dragData.url);
    },
    [dragData]
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 p-3 pb-2 border-b" draggable onDragStart={handleDragStart}>
        <div className="flex items-center gap-1">
          <TooltipProvider delayDuration={0}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Go back"
                  disabled={!canGoBack}
                  onClick={onHistoryBack}
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Back ({history.length} entries)</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider delayDuration={0}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Go forward"
                  disabled={!canGoForward}
                  onClick={onHistoryForward}
                >
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Forward</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider delayDuration={0}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Reload"
                  onClick={onReload}
                  disabled={isLoading}
                >
                  {isLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCcw className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>Refresh preview</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <form onSubmit={handleSubmit} className="flex-1">
          <Input
            value={addressValue}
            onChange={(event) => setAddressValue(event.target.value)}
            className="w-full font-mono text-xs sm:text-sm"
            spellCheck={false}
            autoComplete="off"
            aria-label="Preview address bar"
          />
        </form>
        <TooltipProvider delayDuration={0}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant={highlightMode ? "default" : "outline"}
                size="icon"
                aria-label="Toggle highlight mode"
                onClick={() => setHighlightMode((value) => !value)}
              >
                <Sparkles className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {highlightMode ? "Capturing selection" : "Highlight & extract"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <TooltipProvider delayDuration={0}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                aria-label="Open in new tab"
                onClick={() => onOpenInNewTab?.(url)}
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Open in your browser</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      {highlightMode && (
        <div className="px-3 py-2 border-b bg-muted/60 text-xs sm:text-sm flex items-center gap-2 flex-wrap">
          <span className="font-medium">Highlight mode:</span>
          <span>Select text in the preview, then choose an action.</span>
          <div className="ml-auto flex gap-1">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleSelectionAction("extract")}
            >
              Extract
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleSelectionAction("summarize")}
            >
              Summarize
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleSelectionAction("queue")}
            >
              Queue for crawl
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setHighlightMode(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      {selectionError && (
        <div className="px-3 py-2 text-xs text-destructive bg-destructive/10 border-b">
          {selectionError}
        </div>
      )}
      {highlightMode && selectionText && (
        <div className="px-3 py-2 text-xs bg-muted/50 border-b">
          <span className="font-medium">Selection preview:</span> {selectionText.slice(0, 220)}
          {selectionText.length > 220 ? "…" : ""}
        </div>
      )}
      <div className="relative flex-1">
        <iframe
          key={reloadKey}
          ref={frameRef}
          src={url}
          title="Web preview"
          className="w-full h-full border-0"
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
          onLoad={() => {
            setSelectionError(null);
          }}
        />
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/65 backdrop-blur-sm">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      <Separator />
      <div className="flex items-center justify-between px-3 py-2 text-xs text-muted-foreground">
        <span className="truncate" title={url}>
          {url}
        </span>
        <span className="hidden sm:inline">
          Drag the title bar to add this page to the crawl queue
        </span>
      </div>
    </div>
  );
}
