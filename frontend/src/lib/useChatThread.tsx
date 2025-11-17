"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiClient } from "@/lib/backend/apiClient";
import type { MessageRecord } from "@/lib/backend/types";

interface StartThreadOptions {
  tabId?: string;
  title?: string;
  origin?: string;
}

interface SendMessageInput {
  content: string;
  tabId?: string;
}

interface ChatThreadContextValue {
  currentThreadId: string | null;
  messages: MessageRecord[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
  selectThread: (threadId: string | null) => void;
  startThread: (options?: StartThreadOptions) => Promise<string>;
  sendMessage: (input: SendMessageInput) => Promise<void>;
  reloadThread: () => Promise<void>;
}

const ChatThreadContext = createContext<ChatThreadContextValue | undefined>(undefined);

async function fetchThreadMessages(threadId: string): Promise<MessageRecord[]> {
  const response = await apiClient.get<{ items: MessageRecord[] }>(`/api/threads/${threadId}/messages?limit=200`);
  return response.items ?? [];
}

async function createThreadViaBrowser(tabId: string, options?: StartThreadOptions) {
  const payload = await apiClient.post<{ thread_id: string }>(`/api/browser/tabs/${tabId}/thread`, {
    thread_id: undefined,
    origin: options?.origin ?? "browser",
    title: options?.title,
  });
  return payload.thread_id;
}

async function createThread(options?: StartThreadOptions) {
  const response = await apiClient.post<{ id: string }>("/api/threads", {
    title: options?.title,
    origin: options?.origin ?? "chat",
  });
  return response.id;
}

export function ChatThreadProvider({ children }: { children: ReactNode }) {
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMessages = useCallback(async (threadId: string) => {
    setIsLoading(true);
    try {
      const items = await fetchThreadMessages(threadId);
      setMessages(items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load messages");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!currentThreadId) {
      setMessages([]);
      return;
    }
    loadMessages(currentThreadId);
  }, [currentThreadId, loadMessages]);

  const selectThread = useCallback((threadId: string | null) => {
    setCurrentThreadId(threadId);
  }, []);

  const startThread = useCallback(
    async (options?: StartThreadOptions) => {
      setIsLoading(true);
      try {
        const threadId = options?.tabId
          ? await createThreadViaBrowser(options.tabId, options)
          : await createThread(options);
        setCurrentThreadId(threadId);
        setError(null);
        return threadId;
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unable to start thread";
        setError(message);
        throw err;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const sendMessage = useCallback(
    async ({ content, tabId }: SendMessageInput) => {
      const trimmed = content.trim();
      if (!trimmed) {
        return;
      }
      setIsSending(true);
      try {
        let threadId = currentThreadId;
        if (!threadId) {
          threadId = await startThread({ tabId });
        }
        await apiClient.post("/api/chat", {
          thread_id: threadId,
          tab_id: tabId,
          messages: [{ role: "user", content: trimmed }],
        });
        if (threadId) {
          await loadMessages(threadId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to send message");
        throw err;
      } finally {
        setIsSending(false);
      }
    },
    [currentThreadId, loadMessages, startThread],
  );

  const reloadThread = useCallback(async () => {
    if (!currentThreadId) return;
    await loadMessages(currentThreadId);
  }, [currentThreadId, loadMessages]);

  const value = useMemo<ChatThreadContextValue>(
    () => ({ currentThreadId, messages, isLoading, isSending, error, selectThread, startThread, sendMessage, reloadThread }),
    [currentThreadId, messages, isLoading, isSending, error, selectThread, startThread, sendMessage, reloadThread],
  );

  return <ChatThreadContext.Provider value={value}>{children}</ChatThreadContext.Provider>;
}

export function useChatThread() {
  const context = useContext(ChatThreadContext);
  if (!context) {
    throw new Error("useChatThread must be used within a ChatThreadProvider");
  }
  return context;
}
