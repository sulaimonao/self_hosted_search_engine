"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { AiPanelHeader } from "@/components/ai/AiPanelHeader";
import { ChatInput } from "@/components/ai/ChatInput";
import { ChatMessageList } from "@/components/ai/ChatMessageList";
import { ContextPeek } from "@/components/ai/ContextPeek";
import { TaskList } from "@/components/ai/TaskList";
import { ThreadSummaryBar } from "@/components/ai/ThreadSummaryBar";

export function AiPanel() {
  return (
    <aside className="hidden h-full w-[380px] shrink-0 border-l bg-card/80 p-4 lg:flex lg:flex-col">
      <AiPanelHeader />
      <ThreadSummaryBar />
      <Tabs defaultValue="chat" className="flex flex-1 flex-col overflow-hidden">
        <TabsList className="grid grid-cols-3">
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
