"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Download, Cog, Globe, Menu, MessageSquare, Stethoscope } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import dynamic from "next/dynamic";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { TabsBar } from "@/components/browser/Tabs";
import { AddressBar } from "@/components/browser/AddressBar";
import { NavHistory } from "@/components/browser/nav-history";
import { ModeToggle } from "@/components/browser/ModeToggle";
import { StatusBar } from "@/components/browser/StatusBar";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { ToastGate } from "@/components/notifications/ToastGate";
import { AgentLogPanel } from "@/components/panels/AgentLogPanel";
import { CollectionsPanel } from "@/components/panels/CollectionsPanel";
import { LocalSearchPanel } from "@/components/panels/LocalSearchPanel";
import { ShadowPanel } from "@/components/panels/ShadowPanel";
import { useEvents } from "@/state/useEvents";
import { Panel, useAppStore } from "@/state/useAppStore";
import { resolveBrowserAPI } from "@/lib/browser-ipc";
import { useBrowserIpc } from "@/hooks/useBrowserIpc";
import { SiteInfoPopover } from "@/components/browser/SiteInfoPopover";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";
import { DownloadsTray } from "@/components/browser/DownloadsTray";
import { PermissionPrompt } from "@/components/browser/PermissionPrompt";
import { useStableOnOpenChange } from "@/hooks/useStableOnOpenChange";
import { useUrlBinding } from "@/hooks/useUrlBinding";
import { cn } from "@/lib/utils";
import { DiagnosticsDrawer } from "@/components/browser/DiagnosticsDrawer";
import { useSafeState, useEvent } from "@/lib/react-safe";
import { useRenderLoopGuard } from "@/lib/useRenderLoopGuard";
import { useSafeNavigate } from "@/lib/useSafeNavigate";

const ChatPanel = dynamic(
  () =>
    import("@/components/panels/ChatPanel").then((mod) => ({
      default: mod.ChatPanel,
    })),
  {
    ssr: false,
    loading: () => null,
  },
);

const PANEL_COMPONENT: Record<Panel, JSX.Element> = {
  chat: <ChatPanel />,
  localSearch: <LocalSearchPanel />,
  collections: <CollectionsPanel />,
  shadow: <ShadowPanel />,
  agentLog: <AgentLogPanel />,
};

export function BrowserShell() {
  return <BrowserShellInner />;
}

function BrowserShellInner() {
  useRenderLoopGuard("BrowserShell");

  useUrlBinding();
  useEvents();
  useBrowserIpc();

  const navigate = useSafeNavigate();
  const { activeTab, openPanel, panelOpen } = useAppStore(
    useShallow((state) => ({
      activeTab: state.activeTab?.(),
      openPanel: state.openPanel,
      panelOpen: state.panelOpen,
    })),
  );
  const activePanel = panelOpen;

  const { downloadOrder, downloads, setDownloadsOpen } = useBrowserRuntimeStore(
    useShallow((state) => ({
      downloadOrder: state.downloadOrder,
      downloads: state.downloads,
      setDownloadsOpen: state.setDownloadsOpen,
    })),
  );

  const panelIsOpen = Boolean(activePanel);
  const handlePanelOpenChange = useStableOnOpenChange(panelIsOpen, (next) => {
    if (!next) {
      openPanel(undefined);
    }
  });

  const panelSize = useMemo<"sm" | "md" | "lg" | "xl" | "full">(() => {
    switch (activePanel) {
      case "chat":
        return "xl";
      case "shadow":
      case "agentLog":
        return "lg";
      case "localSearch":
      case "collections":
      default:
        return "md";
    }
  }, [activePanel]);

  const panelWidthClass = useMemo(() => {
    switch (activePanel) {
      case "chat":
        return "w-full max-w-[34rem] border-l bg-background";
      case "shadow":
      case "agentLog":
        return "w-full max-w-[30rem]";
      case "localSearch":
      case "collections":
      default:
        return "w-full max-w-[26rem]";
    }
  }, [activePanel]);

  const activeDownloads = useMemo(
    () => downloadOrder.filter((id) => downloads[id]?.state === "in_progress").length,
    [downloadOrder, downloads],
  );

  const fallbackWebviewRef = useRef<ElectronWebviewElement | null>(null);
  const fallbackIframeRef = useRef<HTMLIFrameElement | null>(null);
  const viewContainerRef = useRef<HTMLDivElement | null>(null);

  const historyRef = useRef(new NavHistory());
  const [fallbackUrl, setFallbackUrl] = useSafeState<string>(() => activeTab?.url ?? "https://wikipedia.org");

  const [supportsWebview, setSupportsWebview] = useSafeState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useSafeState(false);

  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const hasBrowserAPI = Boolean(browserAPI);

  const pageTitle = activeTab?.title || activeTab?.url || "New Tab";

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const ua = window.navigator?.userAgent ?? "";
    setSupportsWebview(/Electron/i.test(ua));
  }, [setSupportsWebview]);

  const updateTabFromHistory = useEvent(
    (url: string, options?: { loading?: boolean; title?: string | null }) => {
      if (!activeTab?.id) {
        return;
      }
      const history = historyRef.current;
      const normalized = url.trim();
      if (!normalized) {
        return;
      }
      const nextTitle =
        options?.title && options.title.trim()
          ? options.title.trim()
          : activeTab.title && activeTab.title.trim()
            ? activeTab.title
            : normalized;
      setFallbackUrl(normalized);
      useAppStore.getState().updateTab(activeTab.id, {
        url: normalized,
        title: nextTitle,
        canGoBack: history.canBack(),
        canGoForward: history.canForward(),
        isLoading: options?.loading ?? false,
        error: null,
      });
    },
  );

  useEffect(() => {
    if (browserAPI || supportsWebview) {
      historyRef.current.reset(activeTab?.url ?? "");
      return;
    }
    const history = historyRef.current;
    const initialUrl = activeTab?.url ?? "https://wikipedia.org";
    history.reset(initialUrl);
    if (initialUrl) {
      updateTabFromHistory(initialUrl, { loading: false });
    }
  }, [activeTab?.id, activeTab?.url, browserAPI, supportsWebview, updateTabFromHistory]);

  useEffect(() => {
    if (browserAPI || supportsWebview) {
      return;
    }
    const url = activeTab?.url ?? "https://wikipedia.org";
    const history = historyRef.current;
    if (!url.trim()) {
      return;
    }
    if (history.current() === url) {
      return;
    }
    history.push(url);
    updateTabFromHistory(history.current(), { loading: true });
  }, [activeTab?.url, browserAPI, supportsWebview, updateTabFromHistory]);

  useEffect(() => {
    if (browserAPI || supportsWebview) {
      return;
    }
    const handler = (event: MessageEvent) => {
      const data = event?.data;
      if (!data || typeof data !== "object") {
        return;
      }
      const type = (data as { type?: unknown }).type;
      if (type !== "browser:navigated") {
        return;
      }
      const url = typeof (data as { url?: unknown }).url === "string" ? data.url : null;
      const title = typeof (data as { title?: unknown }).title === "string" ? data.title : null;
      if (!url || !url.trim()) {
        return;
      }
      const history = historyRef.current;
      history.push(url);
      updateTabFromHistory(history.current(), { loading: false, title });
    };
    window.addEventListener("message", handler);
    return () => {
      window.removeEventListener("message", handler);
    };
  }, [browserAPI, supportsWebview, updateTabFromHistory]);

  useEffect(() => {
    if (!browserAPI || !viewContainerRef.current) {
      return;
    }
    const element = viewContainerRef.current;
    const updateBounds = () => {
      const rect = element.getBoundingClientRect();
      browserAPI.setBounds({
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      });
    };
    updateBounds();
    const observer = new ResizeObserver(() => updateBounds());
    observer.observe(element);
    window.addEventListener("resize", updateBounds);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", updateBounds);
    };
  }, [browserAPI]);

  useEffect(() => {
    if (hasBrowserAPI) {
      return;
    }
    const webview = fallbackWebviewRef.current;
    if (!webview || !activeTab?.url) {
      return;
    }
    try {
      const currentUrl = typeof webview.getURL === "function" ? webview.getURL() : webview.getAttribute("src") || "";
      if (currentUrl !== activeTab.url) {
        if (typeof webview.loadURL === "function") {
          const loadResult = webview.loadURL(activeTab.url);
          if (loadResult instanceof Promise) {
            void loadResult.catch((error) => {
              console.warn("[browser] failed to load fallback webview URL", error);
            });
          }
        } else {
          webview.setAttribute("src", activeTab.url);
        }
      }
    } catch (error) {
      console.warn("[browser] failed to sync fallback webview", error);
    }
  }, [activeTab?.url, hasBrowserAPI]);

  useEffect(() => {
    if (hasBrowserAPI) {
      return;
    }
    const webview = fallbackWebviewRef.current;
    const tabId = activeTab?.id;
    if (!webview || !tabId) {
      return;
    }

    const updateNavigationState = (url?: string) => {
      const store = useAppStore.getState();
      const canGoBack = Boolean(webview.canGoBack?.());
      const canGoForward = Boolean(webview.canGoForward?.());
      const title = typeof webview.getTitle === "function" ? webview.getTitle() : undefined;
      const nextUrl = url ?? (typeof webview.getURL === "function" ? webview.getURL() : undefined) ?? activeTab?.url ?? "";
      store.updateTab(tabId, {
        url: nextUrl,
        canGoBack,
        canGoForward,
        isLoading: false,
        error: null,
        title: title && title.trim() ? title : nextUrl,
      });
    };

    const handleDidNavigate = (event: { url?: string }) => {
      updateNavigationState(event?.url);
    };

    const handleDidStartLoading = () => {
      useAppStore.getState().updateTab(tabId, { isLoading: true });
    };

    const handleDidStopLoading = () => {
      updateNavigationState();
    };

    const handleTitleUpdated = (event: { title?: string }) => {
      if (event?.title) {
        useAppStore.getState().updateTab(tabId, { title: event.title });
      }
    };

    const handleFaviconUpdated = (event: { favicons?: string[] }) => {
      const favicon = Array.isArray(event?.favicons) && event.favicons.length > 0 ? event.favicons[0] : null;
      useAppStore.getState().updateTab(tabId, { favicon });
    };

    const handleDidFailLoad = (_event: unknown, errorCode?: number, errorDescription?: string) => {
      useAppStore.getState().updateTab(tabId, {
        isLoading: false,
        error: {
          code: errorCode,
          description: errorDescription || "Navigation failed",
        },
      });
    };

    const listeners: [string, (...args: unknown[]) => void][] = [
      ["did-start-loading", handleDidStartLoading],
      ["did-stop-loading", handleDidStopLoading],
      ["did-navigate", handleDidNavigate as (...args: unknown[]) => void],
      ["did-navigate-in-page", handleDidNavigate as (...args: unknown[]) => void],
      ["page-title-updated", handleTitleUpdated as (...args: unknown[]) => void],
      ["page-favicon-updated", handleFaviconUpdated as (...args: unknown[]) => void],
      ["did-fail-load", handleDidFailLoad as (...args: unknown[]) => void],
      ["dom-ready", () => updateNavigationState()],
    ];

    listeners.forEach(([event, handler]) => {
      try {
        webview.addEventListener?.(event, handler);
      } catch (error) {
        console.warn(`[browser] failed to attach ${event} listener`, error);
      }
    });

    return () => {
      listeners.forEach(([event, handler]) => {
        try {
          webview.removeEventListener?.(event, handler);
        } catch (error) {
          console.warn(`[browser] failed to detach ${event} listener`, error);
        }
      });
    };
  }, [activeTab?.id, activeTab?.url, hasBrowserAPI]);

  const handleBack = useCallback(() => {
    if (browserAPI) {
      browserAPI.back({ tabId: activeTab?.id });
      return;
    }
    if (supportsWebview) {
      const webview = fallbackWebviewRef.current;
      if (webview?.canGoBack?.()) {
        webview.goBack?.();
      }
      return;
    }
    const history = historyRef.current;
    const previous = history.back();
    const target = previous ?? history.current();
    if (target) {
      updateTabFromHistory(target, { loading: true });
    }
  }, [activeTab?.id, browserAPI, supportsWebview, updateTabFromHistory]);

  const handleForward = useCallback(() => {
    if (browserAPI) {
      browserAPI.forward({ tabId: activeTab?.id });
      return;
    }
    if (supportsWebview) {
      const webview = fallbackWebviewRef.current;
      if (webview?.canGoForward?.()) {
        webview.goForward?.();
      }
      return;
    }
    const history = historyRef.current;
    const next = history.forward();
    const target = next ?? history.current();
    if (target) {
      updateTabFromHistory(target, { loading: true });
    }
  }, [activeTab?.id, browserAPI, supportsWebview, updateTabFromHistory]);

  const handleReload = useCallback(() => {
    if (browserAPI) {
      browserAPI.reload({ tabId: activeTab?.id });
      return;
    }
    if (supportsWebview) {
      const webview = fallbackWebviewRef.current;
      if (webview) {
        webview.reload?.();
      }
      return;
    }
    const history = historyRef.current;
    const url = history.current();
    if (!url) {
      return;
    }
    const iframe = fallbackIframeRef.current;
    if (iframe) {
      try {
        iframe.src = url;
      } catch (error) {
        console.warn("[browser] failed to reload iframe", error);
      }
    }
    updateTabFromHistory(url, { loading: true });
  }, [activeTab?.id, browserAPI, supportsWebview, updateTabFromHistory]);

  const handleIframeLoad = useCallback(() => {
    if (browserAPI || supportsWebview) {
      return;
    }
    const currentUrl = historyRef.current.current() || fallbackUrl;
    if (!currentUrl) {
      return;
    }
    updateTabFromHistory(currentUrl, { loading: false });
  }, [browserAPI, supportsWebview, fallbackUrl, updateTabFromHistory]);

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="border-b bg-background/95">
        <div className="flex items-center justify-between px-4 py-2">
          <TabsBar />
        </div>
        <div className="flex items-center gap-3 px-4 pb-2">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              disabled={!activeTab?.canGoBack}
              onClick={handleBack}
            >
              <ArrowLeft size={16} />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!activeTab?.canGoForward}
              onClick={handleForward}
            >
              <ArrowRight size={16} />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={handleReload}
              disabled={!activeTab}
            >
              <RotateCcw size={16} />
            </Button>
          </div>
          <SiteInfoPopover url={activeTab?.url} />
          <div className="hidden min-w-0 items-center gap-2 sm:flex">
            {activeTab?.favicon ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={activeTab.favicon} alt="" className="h-4 w-4" />
            ) : (
              <Globe size={14} className="text-muted-foreground" />
            )}
            <span className="truncate text-sm text-muted-foreground">{pageTitle}</span>
          </div>
          <div className="flex-1">
            <AddressBar />
          </div>
          <ModeToggle />
          <Button
            variant="outline"
            size="icon"
            onClick={() => setDownloadsOpen(true)}
            title="Downloads"
            className="relative"
          >
            <Download size={16} />
            {activeDownloads > 0 ? (
              <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground">
                {activeDownloads}
              </span>
            ) : null}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="icon" title="Menu">
                <Menu size={16} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              <DropdownMenuItem onSelect={() => { setDownloadsOpen(true); }}>
                Downloads
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => { navigate.push("/control-center"); }}>
                Control Center
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  navigate.push("/history");
                }}
              >
                History
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="icon"
            title="Control Center"
            onClick={() => navigate.push("/control-center")}
          >
            <Cog size={16} />
          </Button>
          <Button
            variant="outline"
            size="icon"
            title="Chat"
            aria-label="Open chat panel"
            onClick={() => openPanel("chat")}
          >
            <MessageSquare size={16} />
          </Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("localSearch")}>🔍</Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("collections")}>📁</Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("shadow")}>🕶️</Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("agentLog")}>🧠</Button>
          <Button
            variant="outline"
            size="icon"
            title="Diagnostics"
            onClick={() => setDiagnosticsOpen(true)}
          >
            <Stethoscope size={16} />
          </Button>
          <NotificationBell />
        </div>
      </header>

      <main ref={viewContainerRef} className="relative flex flex-1 overflow-hidden">
        {hasBrowserAPI ? (
          <div className="h-full w-full" aria-hidden />
        ) : supportsWebview ? (
          <webview
            ref={fallbackWebviewRef}
            src={activeTab?.url ?? "https://wikipedia.org"}
            title={activeTab?.title ?? "tab"}
            className="h-full w-full border-0"
            partition="persist:main"
            allowpopups
          />
        ) : (
          <iframe
            ref={fallbackIframeRef}
            src={fallbackUrl}
            title={activeTab?.title ?? "tab"}
            className="h-full w-full border-0"
            allow="accelerometer; autoplay; clipboard-read; clipboard-write; encrypted-media; geolocation; microphone; camera; midi; payment"
            onLoad={handleIframeLoad}
          />
        )}

        {activeTab?.error ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/80">
            <div className="pointer-events-auto max-w-sm rounded-md border bg-background p-4 shadow">
              <p className="text-sm font-medium">Unable to load page</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {activeTab.error?.description ?? "An unexpected network error occurred."}
              </p>
              <div className="mt-3 flex justify-end">
                <Button size="sm" onClick={() => browserAPI?.reload({ tabId: activeTab.id, ignoreCache: true })}>
                  Retry
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        <Sheet open={panelIsOpen} onOpenChange={handlePanelOpenChange}>
          <SheetContent
            side={activePanel === "localSearch" || activePanel === "collections" ? "left" : "right"}
            size={panelSize}
            className={cn("p-0", panelWidthClass)}
          >
            {activePanel ? PANEL_COMPONENT[activePanel] : null}
          </SheetContent>
        </Sheet>
      </main>

      <StatusBar />
      <DownloadsTray />
      <PermissionPrompt />
      <DiagnosticsDrawer
        open={diagnosticsOpen}
        onOpenChange={setDiagnosticsOpen}
        webviewRef={fallbackWebviewRef}
        browserAPI={browserAPI}
        supportsWebview={supportsWebview}
      />
      <ToastGate />
    </div>
  );
}
