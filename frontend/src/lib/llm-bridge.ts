export interface LlmFramePayload {
  requestId: string;
  frame: string;
}

export interface LlmStreamRequest {
  requestId?: string;
  body?: Record<string, unknown>;
}

export interface LlmStreamResult {
  ok?: boolean;
  requestId?: string;
}

export interface LlmAbortResult {
  ok?: boolean;
  reason?: string;
}

export interface LlmBridge {
  stream?: (payload: LlmStreamRequest) => Promise<LlmStreamResult>;
  abort?: (requestId?: string | null) => Promise<LlmAbortResult | void> | LlmAbortResult | void;
  onFrame?: (handler: (payload: LlmFramePayload) => void) => (() => void) | void;
}

const fallback: LlmBridge = {
  stream: async () => {
    throw new Error('llm bridge unavailable');
  },
  abort: async () => ({ ok: false, reason: 'unsupported' }),
  onFrame: () => () => undefined,
};

declare global {
  interface Window {
    llm?: LlmBridge;
  }
}

export function resolveLlmBridge(): LlmBridge {
  if (typeof window === 'undefined') {
    return fallback;
  }
  const candidate = (window as { llm?: LlmBridge }).llm;
  if (!candidate || typeof candidate !== 'object') {
    return fallback;
  }
  return { ...fallback, ...candidate };
}

export function llmSupports<K extends keyof LlmBridge>(
  bridge: LlmBridge | undefined,
  key: K,
): bridge is LlmBridge & Required<Pick<LlmBridge, K>> {
  return typeof bridge?.[key] === 'function';
}
