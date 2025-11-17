"use client";

import { PanelRightClose, PanelRightOpen, SparklesIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

import { AiPanelHeader } from "@/components/ai/AiPanelHeader";
import { ChatInput } from "@/components/ai/ChatInput";
import { ChatMessageList } from "@/components/ai/ChatMessageList";
import { ContextPeek } from "@/components/ai/ContextPeek";
import { TaskList } from "@/components/ai/TaskList";
import { ThreadSummaryBar } from "@/components/ai/ThreadSummaryBar";

export type AiPanelTab = "chat" | "tasks" | "context";

interface AiPanelProps {
  isOpen: boolean;
  activeTab: AiPanelTab;
  onTabChange: (tab: AiPanelTab) => void;
  onOpen: () => void;
  onClose: () => void;
}

export function AiPanel({ isOpen, activeTab, onTabChange, onOpen, onClose }: AiPanelProps) {
  const collapsed = cn(
    "hidden h-full shrink-0 border-l border-ai-border bg-ai-panel text-fg shadow-soft transition-all duration-normal ease-default lg:flex lg:flex-col",
    isOpen ? "w-[380px] p-4" : "w-12 items-center justify-between px-2 py-4",
  );

  if (!isOpen) {
    return (
      <aside className={collapsed} aria-label="AI panel collapsed">
        <Button variant="ghost" size="icon" onClick={onOpen} title="Open AI panel (⌘⇧A)">
          <PanelRightOpen className="size-4" />
          <span className="sr-only">Open AI panel</span>
        </Button>
        <div className="flex flex-col items-center gap-1 text-[10px] font-semibold tracking-[0.4em] text-fg-muted">
          <SparklesIcon className="size-4" aria-hidden />
          <span className="-rotate-90">AI</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className={collapsed} aria-label="AI panel">
      <div className="mb-3 flex items-center justify-between gap-2">
        <AiPanelHeader />
        <Button variant="ghost" size="icon" onClick={onClose} title="Collapse AI panel">
          <PanelRightClose className="size-4" />
          <span className="sr-only">Collapse AI panel</span>
        </Button>
      </div>
      <ThreadSummaryBar onRequestTabChange={onTabChange} />
      <Tabs value={activeTab} onValueChange={(value) => onTabChange(value as AiPanelTab)} className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="grid grid-cols-3 rounded-xs border border-border-subtle bg-app-card-subtle text-xs">
          <TabsTrigger value="chat">Chat</TabsTrigger>
          <TabsTrigger value="tasks">Tasks</TabsTrigger>
          <TabsTrigger value="context">Context</TabsTrigger>
        </TabsList>
        <TabsContent value="chat" className="flex flex-1 flex-col overflow-hidden">
          <ChatMessageList />
          <ChatInput />
        </TabsContent>
        <TabsContent value="tasks" className="flex flex-1 flex-col overflow-hidden">
          <TaskList />
        </TabsContent>
        <TabsContent value="context" className="flex flex-1 flex-col overflow-hidden">
          <ContextPeek />
        </TabsContent>
      </Tabs>
    </aside>
  );
}
