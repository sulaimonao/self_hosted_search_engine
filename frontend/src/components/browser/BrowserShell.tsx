"use client";

import { ArrowLeft, ArrowRight, RotateCcw, Download, Cog, Globe, Menu } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
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

  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const viewContainerRef = useRef<HTMLDivElement | null>(null);

  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const hasBrowserAPI = Boolean(browserAPI);

  const pageTitle = activeTab?.title || activeTab?.url || "New Tab";

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
    if (activeTab?.url && iframeRef.current) {
      iframeRef.current.src = activeTab.url;
    }
  }, [activeTab?.url, hasBrowserAPI]);

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
              onClick={() => browserAPI?.back({ tabId: activeTab?.id })}
            >
              <ArrowLeft size={16} />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!activeTab?.canGoForward}
              onClick={() => browserAPI?.forward({ tabId: activeTab?.id })}
            >
              <ArrowRight size={16} />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => browserAPI?.reload({ tabId: activeTab?.id })}
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
          <NotificationBell />
        </div>
      </header>

      <main ref={viewContainerRef} className="relative flex flex-1 overflow-hidden">
        {hasBrowserAPI ? (
          <div className="h-full w-full" aria-hidden />
        ) : (
          <iframe
            ref={iframeRef}
            title={activeTab?.title ?? "tab"}
            className="h-full w-full"
            sandbox="allow-same-origin allow-forms allow-scripts allow-popups allow-top-navigation-by-user-activation"
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
      <ToastGate />
    </div>
  );
}
