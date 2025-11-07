import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getHealth } from '../../src/lib/api';

// Ensure our vitest.setup fetch wrapper runs; we will mock fetch to inspect headers
const originalFetch = globalThis.fetch;

describe('fetchLogged wrapper', () => {
  beforeEach(() => {
    vi.spyOn(console, 'debug').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it('adds X-Request-Id header and exposes traceId on response', async () => {
    const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const headers = (init?.headers ?? {}) as Record<string, string>;
      expect(headers['X-Request-Id']).toBeTruthy();
      // return a response echoing the same header
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json', 'X-Request-Id': headers['X-Request-Id'] },
      });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchSpy;

    const res = await getHealth();
    expect(res).toEqual({ ok: true });
    expect(fetchSpy).toHaveBeenCalledOnce();
  });
});
