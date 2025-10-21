"use client";

import { ArrowLeft, ArrowRight, ExternalLink, Loader2, RefreshCcw } from "lucide-react";
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
import type { CrawlScope } from "@/lib/types";

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
  onCrawlDomain?: () => void;
  crawlDisabled?: boolean;
  crawlStatus?: {
    running: boolean;
    statusText: string | null;
    jobId: string | null;
    targetUrl: string | null;
    scope: CrawlScope | null;
    error: string | null;
    lastUpdated: number | null;
  } | null;
  crawlLabel?: string;
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
  onCrawlDomain,
  crawlDisabled = false,
  crawlStatus = null,
  crawlLabel = "Crawl domain",
}: WebPreviewProps) {
  const [addressValue, setAddressValue] = useState(url || DEFAULT_URL);
  useEffect(() => {
    setAddressValue(url);
  }, [url]);

  const [supportsWebview, setSupportsWebview] = useState(false);
  const webviewRef = useRef<ElectronWebviewElement | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const ua = window.navigator?.userAgent ?? "";
    setSupportsWebview(/Electron/i.test(ua) || Boolean(window.appBridge?.supportsWebview));
  }, []);


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
    <div className="flex h-full min-h-0 flex-col">
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
                  onClick={() => {
                    if (supportsWebview) {
                      webviewRef.current?.goBack?.();
                    }
                    onHistoryBack();
                  }}
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
                  onClick={() => {
                    if (supportsWebview) {
                      webviewRef.current?.goForward?.();
                    }
                    onHistoryForward();
                  }}
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
                  onClick={() => {
                    if (supportsWebview) {
                      webviewRef.current?.reload?.();
                    }
                    onReload();
                  }}
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
                variant="outline"
                size="icon"
                aria-label="Open in new tab"
                onClick={() => {
                  if (onOpenInNewTab) {
                    onOpenInNewTab(url);
                  } else if (typeof window !== "undefined") {
                    window.open(url, "_blank", "noopener,noreferrer");
                  }
                }}
              >
                <ExternalLink className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Open in your browser</TooltipContent>
          </Tooltip>
        </TooltipProvider>
        {onCrawlDomain ? (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="whitespace-nowrap"
            onClick={onCrawlDomain}
            disabled={crawlDisabled}
          >
            {crawlStatus?.running ? (
              <>
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                {crawlStatus.statusText ?? "Crawling…"}
              </>
            ) : (
              <>
                <RefreshCcw className="mr-1 h-4 w-4" />
                {crawlLabel}
              </>
            )}
          </Button>
        ) : null}
      </div>
      {crawlStatus?.error ? (
        <div className="px-3 text-xs text-destructive">{crawlStatus.error}</div>
      ) : crawlStatus?.statusText ? (
        <div className="px-3 text-xs text-muted-foreground">
          {crawlStatus.statusText}
        </div>
      ) : null}
      <div className="relative flex-1 min-h-0 w-full overflow-hidden">
        {supportsWebview ? (
          <webview
            ref={webviewRef}
            key={reloadKey}
            src={url}
            className="block h-full w-full border-0"
            partition="persist:main"
            allowpopups
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center rounded-md border border-dashed text-sm text-muted-foreground">
            Preview is available in the desktop app.
          </div>
        )}
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
