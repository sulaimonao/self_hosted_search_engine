"use client";

import { useEffect } from "react";
import { create } from "zustand";

type AgentStep = {
  tool: string | null;
  status: string | null;
  duration_ms?: number | null;
  excerpt?: string | null;
  started_at?: number | null;
  ended_at?: number | null;
  token_in?: number | null;
  token_out?: number | null;
};

type AgentTraceState = {
  stepsByChat: Record<string, Record<string, AgentStep[]>>;
  addStep: (chatId: string, messageId: string, step: AgentStep) => void;
  resetChat: (chatId: string) => void;
};

const DEFAULT_MESSAGE_ID = "__thread__";

export const useAgentTraceStore = create<AgentTraceState>((set) => ({
  stepsByChat: {},
  addStep: (chatId, messageId, step) =>
    set((state) => {
      const chatBucket = state.stepsByChat[chatId] ?? {};
      const messageBucket = chatBucket[messageId] ? [...chatBucket[messageId]] : [];
      messageBucket.push(step);
      return {
        stepsByChat: {
          ...state.stepsByChat,
          [chatId]: {
            ...chatBucket,
            [messageId]: messageBucket,
          },
        },
      };
    }),
  resetChat: (chatId) =>
    set((state) => {
      if (!state.stepsByChat[chatId]) {
        return state;
      }
      const copy = { ...state.stepsByChat };
      delete copy[chatId];
      return { stepsByChat: copy };
    }),
}));

const connections = new Map<string, EventSource>();

export function useAgentTraceSubscription(chatId: string | null | undefined, enabled: boolean) {
  const addStep = useAgentTraceStore((state) => state.addStep);
  const resetChat = useAgentTraceStore((state) => state.resetChat);

  useEffect(() => {
    // Avoid subscribing to EventSource during unit tests. JSDOM or test runners
    // may not emulate SSE correctly and it can cause repeated updates in
    // that environment.
    // eslint-disable-next-line no-process-env
    if (typeof process !== "undefined" && process.env.NODE_ENV === "test") {
      return;
    }
    if (!chatId) {
      return;
    }
    if (!enabled) {
      resetChat(chatId);
      const existing = connections.get(chatId);
      if (existing) {
        existing.close();
        connections.delete(chatId);
      }
      return;
    }

    if (connections.has(chatId)) {
      return;
    }

    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      return;
    }

    const source = new EventSource(`/api/agent/logs?chat_id=${encodeURIComponent(chatId)}`);
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data ?? "{}") as Record<string, unknown>;
        if ((data.type as string) !== "agent_step") {
          return;
        }
        const messageId = typeof data.message_id === "string" && data.message_id.trim()
          ? data.message_id.trim()
          : DEFAULT_MESSAGE_ID;
        addStep(chatId, messageId, {
          tool: typeof data.tool === "string" ? data.tool : null,
          status: typeof data.status === "string" ? data.status : null,
          duration_ms: typeof data.duration_ms === "number" ? data.duration_ms : null,
          excerpt: typeof data.excerpt === "string" ? data.excerpt : null,
          started_at: typeof data.started_at === "number" ? data.started_at : null,
          ended_at: typeof data.ended_at === "number" ? data.ended_at : null,
          token_in: typeof data.token_in === "number" ? data.token_in : null,
          token_out: typeof data.token_out === "number" ? data.token_out : null,
        });
      } catch (error) {
        console.warn("agent trace parse failed", error);
      }
    };
    source.onerror = () => {
      source.close();
      connections.delete(chatId);
    };
    connections.set(chatId, source);

    return () => {
      const existing = connections.get(chatId);
      if (existing) {
        existing.close();
        connections.delete(chatId);
      }
    };
  }, [chatId, enabled, addStep, resetChat]);
}

export function useAgentTrace(chatId: string | null | undefined, messageId: string | null | undefined) {
  return useAgentTraceStore((state) => {
    if (!chatId) {
      return [] as AgentStep[];
    }
    const chatBucket = state.stepsByChat[chatId];
    if (!chatBucket) {
      return [] as AgentStep[];
    }
    const key = messageId && messageId.trim() ? messageId : DEFAULT_MESSAGE_ID;
    return chatBucket[key] ?? [];
  });
}

export type { AgentStep };
