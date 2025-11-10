import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { NextRequest } from 'next/server';

// We will import the Next.js route handler
import * as chatRoute from '../../src/app/api/chat/route';

// Helper to create a minimal NextRequest-like object for our handler
class MockRequest {
  url: string;
  headers: Map<string, string>;
  private _body: unknown;
  constructor(body: unknown, headers: Record<string, string> = {}, url = 'http://localhost/api/chat') {
    this._body = body;
    this.url = url;
    this.headers = new Map<string, string>(Object.entries(headers));
  }
  async json() {
    return this._body;
  }
  get headersObj() {
    return this.headers;
  }
  // align with Web API interface used in route
  get headersLike() {
    return {
      get: (k: string) => this.headers.get(k) ?? null,
    } as Headers;
  }
}

// Patch global fetch in tests to intercept upstream calls
const originalFetch = globalThis.fetch;

function createUpstreamResponse(body: string, init: ResponseInit & { headers?: HeadersInit } = {}) {
  return new Response(body, {
    status: init.status ?? 200,
    headers: init.headers ?? { 'Content-Type': 'application/json', 'X-Request-Id': 'trace-abc' },
  });
}

describe('app/api/chat/route.ts', () => {
  beforeEach(() => {
    vi.spyOn(console, 'debug').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it('adapts Vercel useChat payloads into StreamingTextResponse', async () => {
    const req = new MockRequest(
      {
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'text',
                text: 'Hello world',
              },
            ],
          },
        ],
        body: { model: 'gpt-test' },
      },
      { accept: 'text/plain' },
    );

    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      expect(url.endsWith('/api/chat')).toBe(true);
      const payload = JSON.parse((init?.body as string) ?? '{}');
      expect(payload.stream).toBe(false);
      expect(payload.messages[0].content).toBe('Hello world');
      expect(payload.model).toBe('gpt-test');
      return createUpstreamResponse(JSON.stringify({ answer: 'Hi back!', model: 'gpt-test' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json', 'X-LLM-Model': 'gpt-test', 'X-Request-Id': 'trace-xyz' },
      });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchSpy;

    const result = await chatRoute.POST({
      json: () => req.json(),
      headers: req.headersLike,
    } as unknown as NextRequest);

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(result.headers.get('content-type')).toContain('text/plain');
    expect(result.headers.get('x-llm-model')).toBe('gpt-test');
    expect(await result.text()).toBe('Hi back!');
  });

  it('accepts non-empty text for NDJSON path and proxies to /api/chat', async () => {
    const req = new MockRequest({ text: 'hello there' }, { accept: 'application/x-ndjson' });
    // mock global fetch to capture URL
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      expect(url.endsWith('/api/chat')).toBe(true);
      expect(init?.method).toBe('POST');
      const payload = JSON.parse((init?.body as string) ?? '{}');
      expect(Array.isArray(payload.messages)).toBe(true);
      expect(payload.messages[0].content).toBe('hello there');
      return createUpstreamResponse('', { status: 200, headers: { 'Content-Type': 'application/x-ndjson' } });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchSpy;

    // The route expects a NextRequest with headers.get; provide compatible shape
    const result = await chatRoute.POST({
      json: () => req.json(),
      headers: req.headersLike,
    } as unknown as NextRequest);

    expect(result.status).toBe(200);
    expect(result.headers.get('Content-Type')).toBe('application/x-ndjson');
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it('accepts SSE path and proxies to /api/chat/stream', async () => {
    const req = new MockRequest({ messages: [{ role: 'user', content: 'stream me' }] }, { accept: 'text/event-stream' });
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input.toString();
      expect(url.endsWith('/api/chat/stream')).toBe(true);
      expect(init?.headers && (init.headers as Record<string, string>)['Accept']).toBe('text/event-stream');
      return createUpstreamResponse('', { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchSpy;

    const result = await chatRoute.POST({
      json: () => req.json(),
      headers: req.headersLike,
    } as unknown as NextRequest);

    expect(result.status).toBe(200);
    expect(result.headers.get('Content-Type')).toBe('text/event-stream');
    expect(fetchSpy).toHaveBeenCalledOnce();
  });

  it('returns EMPTY_MESSAGE only when input truly empty (spaces only)', async () => {
    const req = new MockRequest({ messages: [{ role: 'user', content: '   ' }] }, { accept: 'application/x-ndjson' });
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as unknown as typeof fetch;

    const result = await chatRoute.POST({
      json: () => req.json(),
      headers: req.headersLike,
    } as unknown as NextRequest);
    expect(result.status).toBe(400);
    const body = await result.text();
    expect(body).toContain('EMPTY_MESSAGE');
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('normalizes model_not_found to MODEL_NOT_FOUND 400', async () => {
    const req = new MockRequest({ text: 'hi', model: 'does-not-exist' }, { accept: 'application/x-ndjson' });
    const fetchSpy = vi.fn(async () => {
      return createUpstreamResponse(JSON.stringify({ error: 'model_not_found', model: 'does-not-exist' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchSpy;

    const result = await chatRoute.POST({
      json: () => req.json(),
      headers: req.headersLike,
    } as unknown as NextRequest);

    expect(result.status).toBe(400);
    const payload = JSON.parse(await result.text());
    expect(payload.error).toBe('MODEL_NOT_FOUND');
  });
});
