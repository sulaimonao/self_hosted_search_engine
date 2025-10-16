"use client";

import { ArrowLeft, ArrowRight, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
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

const PANEL_COMPONENT: Record<Panel, JSX.Element> = {
  localSearch: <LocalSearchPanel />,
  collections: <CollectionsPanel />,
  chat: <ChatPanel />,
  shadow: <ShadowPanel />,
  agentLog: <AgentLogPanel />,
};

export function BrowserShell() {
  useEvents();

  useBrowserIpc();

  const activeTab = useAppStore((state) => state.activeTab?.());
  const openPanel = useAppStore((state) => state.openPanel);
  const panelOpen = useAppStore((state) => state.panelOpen);

  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const viewContainerRef = useRef<HTMLDivElement | null>(null);

  const browserAPI = useMemo(() => resolveBrowserAPI(), []);
  const hasBrowserAPI = Boolean(browserAPI);

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
              onClick={() => browserAPI?.goBack({ tabId: activeTab?.id })}
            >
              <ArrowLeft size={16} />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!activeTab?.canGoForward}
              onClick={() => browserAPI?.goForward({ tabId: activeTab?.id })}
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
          <AddressBar />
          <ModeToggle />
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
            sandbox="allow-same-origin allow-forms allow-scripts allow-popups allow-popups-to-escape-sandbox"
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

        <Sheet open={Boolean(panelOpen)} onOpenChange={(value) => !value && openPanel(undefined)}>
          <SheetContent
            side={panelOpen === "localSearch" || panelOpen === "collections" ? "left" : "right"}
            className="w-auto p-0"
          >
            {panelOpen ? PANEL_COMPONENT[panelOpen] : null}
          </SheetContent>
        </Sheet>
      </main>

      <StatusBar />
      <ToastGate />
    </div>
  );
}
