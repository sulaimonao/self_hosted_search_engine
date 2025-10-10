"use client";

import { ArrowLeft, ArrowRight, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";

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

const PANEL_COMPONENT: Record<Panel, JSX.Element> = {
  localSearch: <LocalSearchPanel />,
  collections: <CollectionsPanel />,
  chat: <ChatPanel />,
  shadow: <ShadowPanel />,
  agentLog: <AgentLogPanel />,
};

export function BrowserShell() {
  useEvents();

  const activeTab = useAppStore((state) => state.activeTab?.());
  const openPanel = useAppStore((state) => state.openPanel);
  const panelOpen = useAppStore((state) => state.panelOpen);

  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (activeTab?.url && iframeRef.current) {
      iframeRef.current.src = activeTab.url;
    }
  }, [activeTab?.url]);

  return (
    <div className="flex h-full min-h-screen flex-col">
      <header className="border-b bg-background/95">
        <div className="flex items-center justify-between px-4 py-2">
          <TabsBar />
        </div>
        <div className="flex items-center gap-3 px-4 pb-2">
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={() => iframeRef.current?.contentWindow?.history.back()}>
              <ArrowLeft size={16} />
            </Button>
            <Button variant="outline" size="icon" onClick={() => iframeRef.current?.contentWindow?.history.forward()}>
              <ArrowRight size={16} />
            </Button>
            <Button variant="outline" size="icon" onClick={() => iframeRef.current?.contentWindow?.location.reload()}>
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

      <main className="relative flex flex-1 overflow-hidden">
        <iframe ref={iframeRef} title={activeTab?.title ?? "tab"} className="h-full w-full" sandbox="allow-same-origin allow-forms allow-scripts allow-popups allow-popups-to-escape-sandbox" />

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
