"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Download, Cog, Globe, Menu, Stethoscope } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useShallow } from "zustand/react/shallow";

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
import { ModeToggle } from "@/components/browser/ModeToggle";
import { StatusBar } from "@/components/browser/StatusBar";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { ToastGate } from "@/components/notifications/ToastGate";
import { AgentLogPanel } from "@/components/panels/AgentLogPanel";
import { ChatPanel } from "@/components/panels/ChatPanel";
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
import { SettingsSheet } from "@/components/browser/SettingsSheet";
import { useStableOnOpenChange } from "@/hooks/useStableOnOpenChange";
import { useUrlBinding } from "@/hooks/useUrlBinding";
import { cn } from "@/lib/utils";
import { DiagnosticsDrawer } from "@/components/browser/DiagnosticsDrawer";

const PANEL_COMPONENT: Record<Panel, JSX.Element> = {
  localSearch: <LocalSearchPanel />,
  collections: <CollectionsPanel />,
  chat: <ChatPanel />,
  shadow: <ShadowPanel />,
  agentLog: <AgentLogPanel />,
};

export function BrowserShell() {
  useUrlBinding();
  useEvents();
  useBrowserIpc();

  const router = useRouter();
  const { activeTab, openPanel, panelOpen } = useAppStore(
    useShallow((state) => ({
      activeTab: state.activeTab?.(),
      openPanel: state.openPanel,
      panelOpen: state.panelOpen,
    })),
  );

  const { downloadOrder, downloads, setDownloadsOpen } = useBrowserRuntimeStore(
    useShallow((state) => ({
      downloadOrder: state.downloadOrder,
      downloads: state.downloads,
      setDownloadsOpen: state.setDownloadsOpen,
    })),
  );

  const panelIsOpen = Boolean(panelOpen);
  const handlePanelOpenChange = useStableOnOpenChange(panelIsOpen, (next) => {
    if (!next) {
      openPanel(undefined);
    }
  });

  const panelSize = useMemo<"sm" | "md" | "lg" | "xl" | "full">(() => {
    switch (panelOpen) {
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
  }, [panelOpen]);

  const panelWidthClass = useMemo(() => {
    switch (panelOpen) {
      case "chat":
        return "w-full max-w-[34rem]";
      case "shadow":
      case "agentLog":
        return "w-full max-w-[30rem]";
      case "localSearch":
      case "collections":
      default:
        return "w-full max-w-[26rem]";
    }
  }, [panelOpen]);

  const activeDownloads = useMemo(
    () => downloadOrder.filter((id) => downloads[id]?.state === "in_progress").length,
    [downloadOrder, downloads],
  );

  const [settingsOpen, setSettingsOpen] = useState(false);

  const fallbackWebviewRef = useRef<ElectronWebviewElement | null>(null);
  const viewContainerRef = useRef<HTMLDivElement | null>(null);

  const [supportsWebview, setSupportsWebview] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);

  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const hasBrowserAPI = Boolean(browserAPI);

  const pageTitle = activeTab?.title || activeTab?.url || "New Tab";

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const ua = window.navigator?.userAgent ?? "";
    setSupportsWebview(/Electron/i.test(ua));
  }, []);

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
          void webview.loadURL(activeTab.url).catch((error) => {
            console.warn("[browser] failed to load fallback webview URL", error);
          });
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
    const webview = fallbackWebviewRef.current;
    if (webview?.canGoBack?.()) {
      webview.goBack?.();
    }
  }, [browserAPI, activeTab?.id]);

  const handleForward = useCallback(() => {
    if (browserAPI) {
      browserAPI.forward({ tabId: activeTab?.id });
      return;
    }
    const webview = fallbackWebviewRef.current;
    if (webview?.canGoForward?.()) {
      webview.goForward?.();
    }
  }, [browserAPI, activeTab?.id]);

  const handleReload = useCallback(() => {
    if (browserAPI) {
      browserAPI.reload({ tabId: activeTab?.id });
      return;
    }
    const webview = fallbackWebviewRef.current;
    if (webview) {
      webview.reload?.();
    }
  }, [browserAPI, activeTab?.id]);

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
              <DropdownMenuItem
                onSelect={() => {
                  setDownloadsOpen(true);
                }}
              >
                Downloads
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  setSettingsOpen(true);
                }}
              >
                Settings
              </DropdownMenuItem>
              <DropdownMenuItem
                onSelect={() => {
                  router.push("/history");
                }}
              >
                History
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button
            variant="outline"
            size="icon"
            title="Settings"
            onClick={() => setSettingsOpen(true)}
          >
            <Cog size={16} />
          </Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("localSearch")}>🔍</Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("collections")}>📁</Button>
          <Button variant="outline" size="icon" onClick={() => openPanel("chat")}>💬</Button>
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
        ) : (
          supportsWebview ? (
            <webview
              ref={fallbackWebviewRef}
              src={activeTab?.url ?? "https://wikipedia.org"}
              title={activeTab?.title ?? "tab"}
              className="h-full w-full border-0"
              partition="persist:main"
              allowpopups
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-muted/40 text-sm text-muted-foreground">
              Embedded preview requires the desktop app.
            </div>
          )
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
            side={panelOpen === "localSearch" || panelOpen === "collections" ? "left" : "right"}
            size={panelSize}
            className={cn("p-0", panelWidthClass)}
          >
            {panelOpen ? PANEL_COMPONENT[panelOpen] : null}
          </SheetContent>
        </Sheet>
      </main>

      <StatusBar />
      <DownloadsTray />
      <PermissionPrompt />
      <SettingsSheet open={settingsOpen} onOpenChange={setSettingsOpen} />
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
