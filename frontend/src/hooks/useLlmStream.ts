import { useCallback, useSyncExternalStore } from "react";

import type { ChatResponsePayload, ChatStreamEvent } from "@/lib/types";
import { readTextStream } from "@/lib/stream";

type LlmFramePayload = {
  requestId?: string | null;
  frame: string;
};

type LlmBridge = {
  stream: (payload: { requestId: string; body: Record<string, unknown> }) => Promise<unknown> | unknown;
  onFrame: (handler: (payload: LlmFramePayload) => void) => void | (() => void);
  abort?: (requestId?: string | null) => Promise<unknown> | unknown;
};

type LlmStreamSnapshot = {
  requestId: string | null;
  frames: number;
  text: string;
  done: boolean;
  metadata: { model: string | null; traceId: string | null } | null;
  final: ChatResponsePayload | null;
  error: string | null;
};

type LlmStreamStartOptions = {
  requestId: string;
  body: Record<string, unknown>;
};

type LlmStreamHook = {
  state: LlmStreamSnapshot;
  start: (options: LlmStreamStartOptions) => Promise<void>;
  abort: (requestId?: string | null) => void;
  supported: boolean;
};

const defaultSnapshot: LlmStreamSnapshot = {
  requestId: null,
  frames: 0,
  text: "",
  done: false,
  metadata: null,
  final: null,
  error: null,
};

class Store<T> {
  private value: T;
  private listeners = new Set<() => void>();

  constructor(initial: T) {
    this.value = initial;
  }

  get() {
    return this.value;
  }

  set(next: T) {
    if (Object.is(this.value, next)) {
      return;
    }
    this.value = next;
    for (const listener of this.listeners) {
      try {
        listener();
      } catch (error) {
        console.warn("[llm] listener error", error);
      }
    }
  }

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
}

let bridge: LlmBridge | null = null;
let bridgeUnsubscribe: (() => void) | null = null;
const store = new Store<LlmStreamSnapshot>(defaultSnapshot);
let frameAccumulator = "";
let frameAccumulatorRequestId: string | null = null;
let fetchController: AbortController | null = null;
let fetchRequestId: string | null = null;

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

function resolveApi(path: string): string {
  if (!API_BASE) {
    return path;
  }
  return `${API_BASE}${path}`;
}

function update(mutator: (current: LlmStreamSnapshot) => LlmStreamSnapshot) {
  store.set(mutator(store.get()));
}

function getSnapshot() {
  return store.get();
}

function resolveBridge(): LlmBridge | null {
  if (typeof window === "undefined") {
    return null;
  }
  const candidate = (window as { llm?: LlmBridge }).llm;
  if (!candidate || typeof candidate !== "object") {
    return null;
  }
  return candidate;
}

function resetFrameAccumulator(nextRequestId: string | null) {
  frameAccumulator = "";
  frameAccumulatorRequestId = nextRequestId;
}

function ensureBridge() {
  const nextBridge = resolveBridge();
  if (nextBridge === bridge) {
    return;
  }
  if (bridgeUnsubscribe) {
    try {
      bridgeUnsubscribe();
    } catch (error) {
      console.warn("[llm] failed to unsubscribe bridge", error);
    }
    bridgeUnsubscribe = null;
  }
  bridge = nextBridge;
  if (bridge && typeof bridge.onFrame === "function") {
    const unsubscribe = bridge.onFrame(handleFrame);
    bridgeUnsubscribe = typeof unsubscribe === "function" ? unsubscribe : null;
  }
}

function parseSseFrame(raw: string): ChatStreamEvent | null {
  if (typeof raw !== "string" || !raw.trim()) {
    return null;
  }
  const lines = raw.split(/\n/);
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line) {
      continue;
    }
    if (line.startsWith(":")) {
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) {
    return null;
  }
  const payloadText = dataLines.join("\n").trim();
  if (!payloadText) {
    return null;
  }
  try {
    return JSON.parse(payloadText) as ChatStreamEvent;
  } catch {
    return null;
  }
}

function applyFrame(
  current: LlmStreamSnapshot,
  parsed: ChatStreamEvent,
  incomingRequestId: string | null | undefined,
): LlmStreamSnapshot {
  const activeRequest = current.requestId;
  const requestId = incomingRequestId ?? activeRequest;
  if (activeRequest && incomingRequestId && incomingRequestId !== activeRequest) {
    return current;
  }
  if (parsed.type === "metadata") {
    return {
      ...current,
      requestId: requestId ?? current.requestId,
      metadata: {
        model: parsed.model ?? null,
        traceId: parsed.trace_id ?? null,
      },
    };
  }
  if (parsed.type === "delta") {
    const deltaText = parsed.delta ?? parsed.answer ?? "";
    const nextText = deltaText ? current.text + deltaText : current.text;
    return {
      ...current,
      requestId: requestId ?? current.requestId,
      text: nextText,
      frames: deltaText ? current.frames + 1 : current.frames,
      metadata: current.metadata,
      done: false,
      error: null,
    };
  }
  if (parsed.type === "complete") {
    const answer = parsed.payload?.answer ?? current.text;
    return {
      ...current,
      requestId: requestId ?? current.requestId,
      text: answer || current.text,
      done: true,
      final: parsed.payload,
      frames: current.frames,
      error: null,
      metadata:
        parsed.payload?.model || parsed.payload?.trace_id
          ? {
              model: parsed.payload.model ?? current.metadata?.model ?? null,
              traceId: parsed.payload.trace_id ?? current.metadata?.traceId ?? null,
            }
          : current.metadata,
    };
  }
  if (parsed.type === "error") {
    return {
      ...current,
      requestId: requestId ?? current.requestId,
      done: true,
      error: parsed.hint ?? parsed.error ?? "stream_error",
    };
  }
  return current;
}

function handleFrame(payload: LlmFramePayload) {
  if (!payload || typeof payload.frame !== "string") {
    return;
  }
  const rawRequestId =
    typeof payload.requestId === "string" && payload.requestId.trim().length > 0
      ? payload.requestId.trim()
      : null;
  const activeSnapshot = store.get();
  const activeRequestId = activeSnapshot.requestId;

  if (rawRequestId && frameAccumulatorRequestId && rawRequestId !== frameAccumulatorRequestId) {
    resetFrameAccumulator(rawRequestId);
  } else if (rawRequestId && !frameAccumulatorRequestId) {
    frameAccumulatorRequestId = rawRequestId;
  } else if (!frameAccumulatorRequestId && activeRequestId) {
    frameAccumulatorRequestId = activeRequestId;
  }

  frameAccumulator += `${payload.frame}\n\n`;
  const segments = frameAccumulator.split(/\n\n+/);
  frameAccumulator = segments.pop() ?? "";
  if (segments.length === 0) {
    return;
  }

  const requestHint = rawRequestId ?? frameAccumulatorRequestId ?? activeRequestId ?? null;
  for (const segment of segments) {
    const normalized = segment.trim();
    if (!normalized) {
      continue;
    }
    const parsed = parseSseFrame(`${normalized}\n\n`);
    if (!parsed) {
      continue;
    }
    update((current) => applyFrame(current, parsed, requestHint));
    if (parsed.type === "complete" || parsed.type === "error") {
      resetFrameAccumulator(null);
    }
  }
}

export function useLlmStream(): LlmStreamHook {
  ensureBridge();
  const subscribe = useCallback((listener: () => void) => {
    const unsubscribe = store.subscribe(listener);
    ensureBridge();
    return () => {
      try {
        unsubscribe();
      } catch (error) {
        console.warn("[llm] failed to unsubscribe store", error);
      }
    };
  }, []);

  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const start = useCallback(async ({ requestId, body }: LlmStreamStartOptions) => {
    ensureBridge();
    const normalizedBody: Record<string, unknown> = { ...(body ?? {}) };
    if (typeof normalizedBody["request_id"] !== "string" || !normalizedBody["request_id"]) {
      normalizedBody["request_id"] = requestId;
    }
    normalizedBody["stream"] = true;

    store.set({ ...defaultSnapshot, requestId });
    resetFrameAccumulator(requestId);

    const target = bridge;
    if (target && typeof target.stream === "function") {
      try {
        await target.stream({ requestId, body: normalizedBody });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error ?? "stream_failed");
        update((current) => ({ ...current, done: true, error: message }));
        throw error;
      }
      return;
    }

    if (typeof window === "undefined" || typeof window.fetch !== "function") {
      const error = new Error("LLM stream bridge unavailable");
      update((current) => ({ ...current, done: true, error: error.message }));
      throw error;
    }

    const controller = new AbortController();
    if (fetchController) {
      try {
        fetchController.abort();
      } catch (error) {
        console.warn("[llm] failed to abort existing stream", error);
      }
    }
    fetchController = controller;
    fetchRequestId = requestId;

    try {
      const response = await fetch(resolveApi("/api/chat/stream"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(normalizedBody),
        signal: controller.signal,
        credentials: "include",
      });

      const { body } = response;
      if (!response.ok || !body) {
        const message = `stream_http_${response.status}`;
        update((current) => ({ ...current, done: true, error: message }));
        throw new Error(message);
      }

      let buffer = "";
      for await (const chunk of readTextStream(body)) {
        buffer += chunk;
        let index = buffer.indexOf("\n\n");
        while (index !== -1) {
          const frame = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          if (frame.trim()) {
            handleFrame({ requestId, frame });
          }
          index = buffer.indexOf("\n\n");
        }
      }
      if (buffer.trim()) {
        handleFrame({ requestId, frame: buffer });
      }
      update((current) => ({ ...current, done: true }));
    } catch (error) {
      if (controller.signal.aborted) {
        update((current) => ({ ...current, done: true }));
        return;
      }
      const message = error instanceof Error ? error.message : String(error ?? "stream_failed");
      update((current) => ({ ...current, done: true, error: message }));
      throw error instanceof Error ? error : new Error(message);
    } finally {
      if (fetchController === controller) {
        fetchController = null;
        fetchRequestId = null;
      }
    }
  }, []);

  const abort = useCallback(
    (requestId?: string | null) => {
      ensureBridge();
      const target = bridge;
      const effectiveId = requestId ?? store.get().requestId;
      if (target && typeof target.abort === "function") {
        try {
          target.abort(effectiveId);
        } catch (error) {
          console.warn("[llm] abort failed", error);
        }
      }
      if (
        fetchController &&
        (!effectiveId || !fetchRequestId || effectiveId === fetchRequestId)
      ) {
        try {
          fetchController.abort();
        } catch (error) {
          console.warn("[llm] failed to abort fetch stream", error);
        }
        fetchController = null;
        fetchRequestId = null;
      }
      if (effectiveId) {
        if (frameAccumulatorRequestId && frameAccumulatorRequestId === effectiveId) {
          resetFrameAccumulator(null);
        }
        update((current) =>
          current.requestId === effectiveId ? { ...current, done: true } : current,
        );
      }
    },
    [],
  );

  const supported = Boolean(resolveBridge()) ||
    (typeof window !== "undefined" && typeof window.fetch === "function");

  return {
    state: snapshot,
    start,
    abort,
    supported,
  };
}
