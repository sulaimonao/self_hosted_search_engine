'use client';

import { useSyncExternalStore } from 'react';

import type { ChatResponsePayload } from '@/lib/types';
import {
  type LlmBridge,
  type LlmFramePayload,
  type LlmStreamRequest,
  resolveLlmBridge,
  llmSupports,
} from '@/lib/llm-bridge';

interface StreamMetadata {
  model: string | null;
  traceId: string | null;
}

interface StreamState {
  supported: boolean;
  requestId: string | null;
  text: string;
  frames: number;
  done: boolean;
  error: string | null;
  metadata: StreamMetadata | null;
  payload: ChatResponsePayload | null;
}

export interface LlmStreamCompletion {
  requestId: string;
  payload: ChatResponsePayload;
  frames: number;
  text: string;
  metadata: StreamMetadata;
}

const initialState: StreamState = {
  supported: false,
  requestId: null,
  text: '',
  frames: 0,
  done: false,
  error: null,
  metadata: null,
  payload: null,
};

let state: StreamState = { ...initialState };
const listeners = new Set<() => void>();
let bridge: LlmBridge | null = null;
let unsubscribeBridge: (() => void) | null = null;
const pending = new Map<string, { resolve: (value: LlmStreamCompletion) => void; reject: (error: unknown) => void }>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function setState(next: StreamState | ((prev: StreamState) => StreamState)) {
  const updated = typeof next === 'function' ? (next as (prev: StreamState) => StreamState)(state) : next;
  if (updated !== state) {
    state = updated;
    emit();
  }
}

function updateState(patch: Partial<StreamState> | ((prev: StreamState) => StreamState)) {
  if (typeof patch === 'function') {
    setState(patch as (prev: StreamState) => StreamState);
    return;
  }
  setState({ ...state, ...patch });
}

function getSnapshot(): StreamState {
  return state;
}

function getServerSnapshot(): StreamState {
  return initialState;
}

function ensureBridge() {
  if (typeof window === 'undefined') {
    return;
  }
  if (bridge && unsubscribeBridge) {
    return;
  }
  bridge = resolveLlmBridge();
  const supported = llmSupports(bridge, 'stream') && llmSupports(bridge, 'onFrame');
  updateState((prev) => ({ ...prev, supported }));
  if (llmSupports(bridge, 'onFrame')) {
    const unsubscribe = bridge.onFrame?.((payload) => handleFrame(payload)) || null;
    unsubscribeBridge = typeof unsubscribe === 'function' ? unsubscribe : null;
  } else {
    unsubscribeBridge = null;
  }
}

function teardownBridge() {
  if (unsubscribeBridge) {
    try {
      unsubscribeBridge();
    } catch (error) {
      console.warn('[llm] failed to unsubscribe bridge listener', error);
    }
    unsubscribeBridge = null;
  }
  bridge = null;
  updateState((prev) => ({ ...prev, supported: false }));
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  ensureBridge();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      teardownBridge();
    }
  };
}

function createRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function safeParse(json: string): any {
  if (!json) {
    return {};
  }
  try {
    return JSON.parse(json);
  } catch (error) {
    console.warn('[llm] failed to parse SSE payload', error);
    return {};
  }
}

function parseSseFrame(frame: string): { event: string; data: string } {
  const lines = frame.split(/\r?\n/);
  const data: string[] = [];
  let event = 'message';
  for (const line of lines) {
    if (!line || line.startsWith(':')) {
      continue;
    }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() || 'message';
      continue;
    }
    if (line.startsWith('data:')) {
      data.push(line.slice(5).trim());
    }
  }
  return { event, data: data.join('') };
}

function normalizeMetadata(
  previous: StreamMetadata | null,
  patch: { model?: unknown; trace_id?: unknown; traceId?: unknown },
): StreamMetadata {
  const model = typeof patch.model === 'string' ? patch.model : previous?.model ?? null;
  const trace =
    typeof patch.trace_id === 'string'
      ? patch.trace_id
      : typeof patch.traceId === 'string'
        ? patch.traceId
        : previous?.traceId ?? null;
  return { model, traceId: trace };
}

function resolveDeltaText(payload: any): string {
  if (typeof payload?.delta === 'string') {
    return payload.delta;
  }
  if (typeof payload?.answer === 'string') {
    return payload.answer;
  }
  return '';
}

function handleFrame(message: unknown) {
  const payload = message as LlmFramePayload | undefined;
  if (!payload || typeof payload.requestId !== 'string' || typeof payload.frame !== 'string') {
    return;
  }
  const { requestId, frame } = payload;
  const hasPending = pending.has(requestId);
  if (!hasPending && state.requestId && requestId !== state.requestId) {
    return;
  }
  const { event, data } = parseSseFrame(frame);
  if (!data && event !== 'complete') {
    return;
  }

  if (event === 'metadata') {
    const parsed = safeParse(data);
    const metadata = normalizeMetadata(state.metadata, parsed ?? {});
    updateState((prev) => {
      if (prev.requestId && prev.requestId !== requestId) {
        return prev;
      }
      return { ...prev, requestId, metadata };
    });
    return;
  }

  if (event === 'delta' || event === 'message') {
    const parsed = safeParse(data);
    const deltaText = resolveDeltaText(parsed);
    if (!deltaText) {
      return;
    }
    updateState((prev) => {
      if (prev.requestId && prev.requestId !== requestId) {
        return prev;
      }
      const nextText = prev.text + deltaText;
      return {
        ...prev,
        requestId,
        text: nextText,
        frames: prev.frames + 1,
        done: false,
        error: null,
      };
    });
    return;
  }

  if (event === 'complete') {
    const parsed = safeParse(data);
    const payloadData = parsed?.payload as ChatResponsePayload | undefined;
    if (!payloadData) {
      return;
    }
    const metadata = normalizeMetadata(state.metadata, parsed ?? {});
    updateState((prev) => {
      if (prev.requestId && prev.requestId !== requestId) {
        return prev;
      }
      const answerText = payloadData.answer?.toString()?.trim() ?? prev.text;
      return {
        ...prev,
        requestId,
        text: answerText,
        frames: prev.frames,
        done: true,
        error: null,
        metadata,
        payload: payloadData,
      };
    });
    const entry = pending.get(requestId);
    if (entry) {
      const current = state;
      pending.delete(requestId);
      entry.resolve({
        requestId,
        payload: payloadData,
        frames: current.frames,
        text: current.text,
        metadata,
      });
    }
    return;
  }

  if (event === 'error') {
    const parsed = safeParse(data);
    const messageText =
      typeof parsed?.hint === 'string'
        ? parsed.hint
        : typeof parsed?.error === 'string'
          ? parsed.error
          : 'stream error';
    updateState((prev) => {
      if (prev.requestId && prev.requestId !== requestId) {
        return prev;
      }
      return {
        ...prev,
        requestId,
        done: true,
        error: messageText,
      };
    });
    const entry = pending.get(requestId);
    if (entry) {
      pending.delete(requestId);
      entry.reject(new Error(messageText));
    }
  }
}

async function abortActive(reason?: string) {
  if (!state.requestId) {
    return;
  }
  ensureBridge();
  const activeId = state.requestId;
  const currentBridge = bridge;
  if (currentBridge && llmSupports(currentBridge, 'abort')) {
    try {
      await currentBridge.abort?.(activeId);
    } catch (error) {
      console.warn('[llm] abort failed', error);
    }
  }
  const entry = pending.get(activeId);
  if (entry) {
    pending.delete(activeId);
    const abortError = new Error(reason || 'Stream aborted');
    abortError.name = 'AbortError';
    entry.reject(abortError);
  }
  updateState((prev) => {
    if (prev.requestId !== activeId) {
      return prev;
    }
    return { ...prev, done: true };
  });
}

export function useLlmStream() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const start = async (request: LlmStreamRequest): Promise<LlmStreamCompletion> => {
    ensureBridge();
    if (!bridge || !llmSupports(bridge, 'stream')) {
      throw new Error('llm bridge unsupported');
    }
    if (state.requestId && state.requestId !== request.requestId) {
      await abortActive('Replaced by new request');
    }
    const requestId = request.requestId && request.requestId.trim().length > 0
      ? request.requestId.trim()
      : createRequestId();

    const entry = pending.get(requestId);
    if (entry) {
      pending.delete(requestId);
      entry.reject(new Error('Stream superseded'));
    }

    updateState({
      supported: state.supported || true,
      requestId,
      text: '',
      frames: 0,
      done: false,
      error: null,
      metadata: null,
      payload: null,
    });

    const completion = new Promise<LlmStreamCompletion>((resolve, reject) => {
      pending.set(requestId, { resolve, reject });
    });

    void Promise.resolve(
      bridge.stream?.({ requestId, body: request.body ?? {} }) ?? Promise.reject(new Error('llm stream unavailable')),
    ).catch((error) => {
      if (pending.has(requestId)) {
        pending.get(requestId)?.reject(error);
        pending.delete(requestId);
      }
      updateState((prev) => {
        if (prev.requestId !== requestId) {
          return prev;
        }
        return { ...prev, done: true, error: error instanceof Error ? error.message : String(error ?? 'stream error') };
      });
    });

    return completion;
  };

  const abort = async () => {
    await abortActive();
  };

  return {
    supported: snapshot.supported,
    state: snapshot,
    stream: start,
    abort,
  } as const;
}
