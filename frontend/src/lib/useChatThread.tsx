"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiClient } from "@/lib/backend/apiClient";
import type { MessageRecord, ThreadRecord } from "@/lib/backend/types";
import type { ChatResponsePayload } from "@/lib/types";

interface StartThreadOptions {
  tabId?: string;
  title?: string;
  origin?: string;
  metadata?: Record<string, unknown>;
}

interface SendMessageInput {
  content: string;
  tabId?: string;
}

interface ChatThreadContextValue {
  currentThreadId: string | null;
  currentThread: ThreadRecord | null;
  messages: MessageRecord[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
  selectThread: (threadId: string | null) => void;
  startThread: (options?: StartThreadOptions) => Promise<string>;
  sendMessage: (input: SendMessageInput) => Promise<ChatResponsePayload | null>;
  reloadThread: () => Promise<void>;
}

const ChatThreadContext = createContext<ChatThreadContextValue | undefined>(undefined);

async function fetchThreadMessages(threadId: string): Promise<MessageRecord[]> {
  const response = await apiClient.get<{ items: MessageRecord[] }>(`/api/threads/${threadId}/messages?limit=200`);
  return response.items ?? [];
}

async function fetchThreadRecord(threadId: string): Promise<ThreadRecord> {
  const response = await apiClient.get<{ thread: ThreadRecord }>(`/api/threads/${threadId}`);
  return response.thread;
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
  const response = await apiClient.post<{ id: string; thread?: ThreadRecord }>("/api/threads", {
    title: options?.title,
    origin: options?.origin ?? "chat",
    metadata: options?.metadata,
  });
  return { id: response.id, thread: response.thread ?? null };
}

export function ChatThreadProvider({ children }: { children: ReactNode }) {
  const [currentThreadId, setCurrentThreadId] = useState<string | null>(null);
  const [currentThread, setCurrentThread] = useState<ThreadRecord | null>(null);
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

  const loadThreadRecord = useCallback(async (threadId: string) => {
    try {
      const thread = await fetchThreadRecord(threadId);
      setCurrentThread(thread);
    } catch (err) {
      console.error("Failed to load thread", err);
    }
  }, []);

  useEffect(() => {
    if (!currentThreadId) {
      setMessages([]);
      setCurrentThread(null);
      return;
    }
    loadMessages(currentThreadId);
    loadThreadRecord(currentThreadId);
  }, [currentThreadId, loadMessages, loadThreadRecord]);

  const selectThread = useCallback((threadId: string | null) => {
    setCurrentThreadId(threadId);
  }, []);

  const startThread = useCallback(
    async (options?: StartThreadOptions) => {
      setIsLoading(true);
      try {
        let createdThread: ThreadRecord | null = null;
        let threadId: string;
        if (options?.tabId) {
          if (options?.metadata) {
            const created = await createThread(options);
            threadId = created.id;
            createdThread = created.thread;
            await apiClient.post(`/api/browser/tabs/${options.tabId}/thread`, {
              thread_id: threadId,
              origin: options.origin ?? "browser",
              title: options.title,
            });
          } else {
            threadId = await createThreadViaBrowser(options.tabId, options);
          }
        } else {
          const created = await createThread(options);
          threadId = created.id;
          createdThread = created.thread;
        }
        setCurrentThreadId(threadId);
        if (createdThread) {
          setCurrentThread(createdThread);
        }
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
        return null;
      }
      setIsSending(true);
      try {
        let threadId = currentThreadId;
        if (!threadId) {
          threadId = await startThread({ tabId });
        }
        const response = await apiClient.post<ChatResponsePayload>("/api/chat", {
          thread_id: threadId,
          tab_id: tabId,
          messages: [{ role: "user", content: trimmed }],
        });
        if (threadId) {
          await loadMessages(threadId);
        }
        return response ?? null;
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
    await Promise.all([loadMessages(currentThreadId), loadThreadRecord(currentThreadId)]);
  }, [currentThreadId, loadMessages, loadThreadRecord]);

  const value = useMemo<ChatThreadContextValue>(
    () => ({
      currentThreadId,
      currentThread,
      messages,
      isLoading,
      isSending,
      error,
      selectThread,
      startThread,
      sendMessage,
      reloadThread,
    }),
    [currentThreadId, currentThread, messages, isLoading, isSending, error, selectThread, startThread, sendMessage, reloadThread],
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
