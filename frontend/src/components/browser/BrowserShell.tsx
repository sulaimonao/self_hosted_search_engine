"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Download, Cog, Globe, Menu, MessageSquare, Stethoscope, Share2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useId } from "react";
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
import { AddressBar, ADDRESS_BAR_INPUT_ID } from "@/components/browser/AddressBar";
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
import { KnowledgeGraphPanel } from "@/components/KnowledgeGraphPanel";
import { resolveBrowserAPI, type BrowserNavError } from "@/lib/browser-ipc";
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
import { getDefaultNewTabUrl } from "@/components/browser/getDefaultNewTabUrl";

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
  knowledgeGraph: <KnowledgeGraphPanel />,
};

function toBrowserNavError(error: unknown, fallback = "Navigation failed"): BrowserNavError {
  let code: number | undefined;
  let description = fallback;

  if (typeof error === "object" && error !== null) {
    const codeCandidate =
      typeof (error as { errorCode?: unknown }).errorCode === "number"
        ? ((error as { errorCode?: number }).errorCode as number)
        : typeof (error as { code?: unknown }).code === "number"
          ? ((error as { code?: number }).code as number)
          : undefined;
    if (typeof codeCandidate === "number") {
      code = codeCandidate;
    }
    const rawDescription =
      typeof (error as { errorDescription?: unknown }).errorDescription === "string"
        ? ((error as { errorDescription?: string }).errorDescription as string)
        : typeof (error as { description?: unknown }).description === "string"
          ? ((error as { description?: string }).description as string)
          : error instanceof Error && typeof error.message === "string"
            ? error.message
            : null;
    if (rawDescription && rawDescription.trim()) {
      description = rawDescription.trim();
    }
  } else if (typeof error === "string" && error.trim()) {
    description = error.trim();
  }

  if (!description) {
    description = fallback;
  }

  return { code, description };
}

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

  const activeDownloads = useMemo(() => {
    return downloadOrder.filter((id) => {
      const state = downloads[id]?.state;
      return state === "in_progress" || state === "paused";
    }).length;
  }, [downloadOrder, downloads]);
  const downloadsLabel =
    activeDownloads > 0
      ? `Open downloads tray. ${activeDownloads} active download${activeDownloads === 1 ? "" : "s"}.`
      : "Open downloads tray.";

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
  const backDescriptionId = useId();
  const forwardDescriptionId = useId();
  const reloadDescriptionId = useId();
  const downloadsDescriptionId = useId();
  const menuDescriptionId = useId();
  const controlCenterDescriptionId = useId();
  const chatDescriptionId = useId();
  const localSearchDescriptionId = useId();
  const collectionsDescriptionId = useId();
  const shadowDescriptionId = useId();
  const agentLogDescriptionId = useId();
  const diagnosticsDescriptionId = useId();
  const knowledgeGraphDescriptionId = useId();

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
    const getExpectedOrigin = () => {
      const current = historyRef.current.current() || fallbackUrl;
      if (!current || !current.trim()) {
        return null;
      }
      try {
        return new URL(current).origin;
      } catch {
        return null;
      }
    };
    const handler = (event: MessageEvent) => {
      const iframeWindow = fallbackIframeRef.current?.contentWindow;
      if (!iframeWindow || event.source !== iframeWindow) {
        return;
      }
      const expectedOrigin = getExpectedOrigin();
      if (!expectedOrigin || event.origin !== expectedOrigin) {
        return;
      }
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
  }, [browserAPI, fallbackUrl, supportsWebview, updateTabFromHistory]);

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
    const tabId = activeTab?.id;
    const targetUrl = activeTab?.url;
    if (!webview || !tabId || !targetUrl) {
      return;
    }
    const pushFallbackError = (error: unknown) => {
      const normalized = toBrowserNavError(error);
      useAppStore.getState().updateTab(tabId, {
        isLoading: false,
        error: normalized,
      });
    };
    try {
      const currentUrl = typeof webview.getURL === "function" ? webview.getURL() : webview.getAttribute("src") || "";
      if (currentUrl !== targetUrl) {
        if (typeof webview.loadURL === "function") {
          const loadResult = webview.loadURL(targetUrl);
          if (loadResult instanceof Promise) {
            void loadResult.catch((error) => {
              console.warn("[browser] failed to load fallback webview URL", error);
              pushFallbackError(error);
            });
          }
        } else {
          webview.setAttribute("src", targetUrl);
        }
      }
    } catch (error) {
      console.warn("[browser] failed to sync fallback webview", error);
      pushFallbackError(error);
    }
  }, [activeTab?.id, activeTab?.url, hasBrowserAPI]);

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
          description: errorDescription?.trim() || "Navigation failed",
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

  const handleKeyboardShortcuts = useEvent((event: KeyboardEvent) => {
    if (event.defaultPrevented) {
      return;
    }
    const modifierPressed = event.metaKey || event.ctrlKey;
    if (!modifierPressed || event.repeat) {
      return;
    }

    const key = event.key.toLowerCase();
    const store = useAppStore.getState();
    const tabs = store.tabs ?? [];
    const resolvedActiveId = store.activeTabId ?? tabs[0]?.id ?? null;

    const prevent = () => {
      event.preventDefault();
      event.stopPropagation();
    };

    const focusAddressBar = () => {
      const input = document.getElementById(ADDRESS_BAR_INPUT_ID) as HTMLInputElement | null;
      if (input) {
        input.focus();
        input.select();
      }
    };

    const cycleTab = (direction: 1 | -1) => {
      if (tabs.length <= 1) {
        return;
      }
      const currentIndex = tabs.findIndex((tab) => tab.id === resolvedActiveId);
      if (currentIndex < 0) {
        return;
      }
      const nextIndex = (currentIndex + direction + tabs.length) % tabs.length;
      const target = tabs[nextIndex];
      if (target) {
        store.setActive(target.id);
      }
    };

    if (key === "l" && !event.shiftKey && !event.altKey) {
      prevent();
      focusAddressBar();
      return;
    }

    if (key === "t" && !event.shiftKey && !event.altKey) {
      prevent();
      store.addTab(getDefaultNewTabUrl());
      return;
    }

    if (key === "w" && !event.shiftKey && !event.altKey && resolvedActiveId) {
      prevent();
      store.closeTab(resolvedActiveId);
      return;
    }

    if (key === "tab" && !event.altKey) {
      prevent();
      cycleTab(event.shiftKey ? -1 : 1);
      return;
    }

    if (key === "p" && event.shiftKey && !event.altKey) {
      prevent();
      store.setIncognitoMode(!store.incognitoMode);
    }
  });

  useEffect(() => {
    const handler = (event: KeyboardEvent) => handleKeyboardShortcuts(event);
    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
    };
  }, [handleKeyboardShortcuts]);

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
  const handleIframeError = useCallback(() => {
    if (browserAPI || supportsWebview) {
      return;
    }
    const tabId = activeTab?.id;
    if (!tabId) {
      return;
    }
    useAppStore.getState().updateTab(tabId, {
      isLoading: false,
      error: { description: "The network request failed before the page could load." },
    });
  }, [activeTab?.id, browserAPI, supportsWebview]);
  const handleOpenExternal = useCallback(() => {
    if (!activeTab?.url) {
      return;
    }
    const url = activeTab.url;
    if (browserAPI && typeof browserAPI.openExternal === "function") {
      void browserAPI
        .openExternal(url)
        .catch((error) => console.warn("[browser] failed to open external url", error));
      return;
    }
    if (typeof window !== "undefined") {
      try {
        window.open(url, "_blank", "noopener,noreferrer");
      } catch (error) {
        console.warn("[browser] failed to open window", error);
      }
    }
  }, [activeTab?.url, browserAPI]);

  return (
    <div className="flex h-full min-h-0 flex-col">
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
              aria-label="Go back"
              aria-describedby={backDescriptionId}
            >
              <ArrowLeft size={16} aria-hidden="true" />
              <span id={backDescriptionId} className="sr-only">
                Go to the previous page in the current tab
              </span>
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!activeTab?.canGoForward}
              onClick={handleForward}
              aria-label="Go forward"
              aria-describedby={forwardDescriptionId}
            >
              <ArrowRight size={16} aria-hidden="true" />
              <span id={forwardDescriptionId} className="sr-only">
                Go to the next page in the current tab
              </span>
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={handleReload}
              disabled={!activeTab}
              aria-label="Reload page"
              aria-describedby={reloadDescriptionId}
            >
              <RotateCcw size={16} aria-hidden="true" />
              <span id={reloadDescriptionId} className="sr-only">
                Refreshes the current page
              </span>
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
            aria-label={downloadsLabel}
            aria-describedby={downloadsDescriptionId}
          >
            <Download size={16} aria-hidden="true" />
            <span id={downloadsDescriptionId} className="sr-only">
              Opens the downloads tray
            </span>
            {activeDownloads > 0 ? (
              <span
                className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] text-primary-foreground"
                aria-hidden="true"
              >
                {activeDownloads}
              </span>
            ) : null}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="icon"
                title="Menu"
                aria-label="Open browser menu"
                aria-describedby={menuDescriptionId}
              >
                <Menu size={16} aria-hidden="true" />
                <span id={menuDescriptionId} className="sr-only">
                  Access history, downloads, and other pages
                </span>
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
            aria-label="Open Control Center"
            aria-describedby={controlCenterDescriptionId}
          >
            <Cog size={16} aria-hidden="true" />
            <span id={controlCenterDescriptionId} className="sr-only">
              Opens browser settings and controls
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            title="Chat"
            onClick={() => openPanel("chat")}
            aria-label="Open chat panel"
            aria-describedby={chatDescriptionId}
          >
            <MessageSquare size={16} aria-hidden="true" />
            <span id={chatDescriptionId} className="sr-only">
              Opens the chat side panel
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => openPanel("localSearch")}
            aria-label="Open local search panel"
            aria-describedby={localSearchDescriptionId}
          >
            <span aria-hidden="true" role="img">
              🔍
            </span>
            <span id={localSearchDescriptionId} className="sr-only">
              Browse files discovered on this device
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => openPanel("knowledgeGraph")}
            aria-label="Open knowledge graph"
            aria-describedby={knowledgeGraphDescriptionId}
          >
            <Share2 size={16} aria-hidden="true" />
            <span id={knowledgeGraphDescriptionId} className="sr-only">
              Inspect the crawl knowledge graph
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => openPanel("collections")}
            aria-label="Open collections panel"
            aria-describedby={collectionsDescriptionId}
          >
            <span aria-hidden="true" role="img">
              📁
            </span>
            <span id={collectionsDescriptionId} className="sr-only">
              Review saved collections and folders
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => openPanel("shadow")}
            aria-label="Open shadow panel"
            aria-describedby={shadowDescriptionId}
          >
            <span aria-hidden="true" role="img">
              🕶️
            </span>
            <span id={shadowDescriptionId} className="sr-only">
              Manage shadow browsing tools
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={() => openPanel("agentLog")}
            aria-label="Open agent log"
            aria-describedby={agentLogDescriptionId}
          >
            <span aria-hidden="true" role="img">
              🧠
            </span>
            <span id={agentLogDescriptionId} className="sr-only">
              View the agent activity log
            </span>
          </Button>
          <Button
            variant="outline"
            size="icon"
            title="Diagnostics"
            onClick={() => setDiagnosticsOpen(true)}
            aria-label="Open diagnostics panel"
            aria-describedby={diagnosticsDescriptionId}
          >
            <Stethoscope size={16} aria-hidden="true" />
            <span id={diagnosticsDescriptionId} className="sr-only">
              Run diagnostics for troubleshooting
            </span>
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
            partition={activeTab?.sessionPartition ?? "persist:main"}
            allowpopups
          />
        ) : (
          <iframe
            ref={fallbackIframeRef}
            src={fallbackUrl}
            title={activeTab?.title ?? "tab"}
            className="h-full w-full border-0"
            allow="accelerometer; autoplay; clipboard-read; encrypted-media; geolocation; microphone; camera"
            onLoad={handleIframeLoad}
            onError={handleIframeError}
          />
        )}

        {activeTab?.error ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/80">
            <div className="pointer-events-auto max-w-sm rounded-md border bg-background p-4 shadow">
              <p className="text-sm font-medium">Unable to load page</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {activeTab.error?.description?.trim() || "An unexpected network error occurred."}
              </p>
              {typeof activeTab.error?.code === "number" ? (
                <p className="mt-1 text-[11px] font-mono text-muted-foreground">Error code {activeTab.error.code}</p>
              ) : null}
              {activeTab.url ? (
                <p className="mt-2 truncate text-[11px] text-muted-foreground" title={activeTab.url}>
                  {activeTab.url}
                </p>
              ) : null}
              <div className="mt-3 space-y-2 text-[11px] text-muted-foreground">
                <div className="rounded bg-muted/60 p-2 font-mono leading-relaxed text-foreground/80">
                  {(activeTab.error?.description?.trim() || "Navigation failed.")
                    .split("\n")
                    .map((line, index) => (
                      <span key={index} className="block">
                        {line}
                      </span>
                    ))}
                </div>
                <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => setDiagnosticsOpen(true)}>
                  View developer diagnostics
                </Button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!activeTab.url}
                  onClick={handleOpenExternal}
                >
                  Open in system browser
                </Button>
                <Button size="sm" onClick={handleReload}>
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
