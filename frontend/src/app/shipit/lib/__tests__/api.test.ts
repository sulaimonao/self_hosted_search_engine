import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchLlmModels,
  runHybridSearch,
  triggerDiagnostics,
  openProgressStream,
  type HybridSearchResult,
} from "@/app/shipit/lib/api";

const originalFetch = global.fetch;
const OriginalEventSource = global.EventSource;

describe("shipit api helpers", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
    global.EventSource = OriginalEventSource;
  });

  it("fetches model inventory from the llm models endpoint", async () => {
    const response = {
      chat_models: ["gpt-oss", "gemma3"],
      configured: { primary: "gpt-oss", fallback: "gemma3" },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(input).toContain("/api/llm/llm_models");
      return new Response(JSON.stringify(response), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const models = await fetchLlmModels();
    expect(models.chat_models).toEqual(["gpt-oss", "gemma3"]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("falls back to keyword search when hybrid search is unavailable", async () => {
    const hybridResponse = new Response("not found", { status: 404 });
    const fallbackPayload = {
      hits: [
        {
          url: "https://example.com",
          title: "Example",
          snippet: "hello",
          score: 0.8,
          source: "keyword",
        },
      ],
    } satisfies Record<string, unknown>;
    const fallbackResponse = new Response(JSON.stringify(fallbackPayload), { status: 200 });
    const fetchMock = vi
      .fn(async (input: RequestInfo | URL) => {
        if (typeof input === "string" && input.includes("/api/index/hybrid_search")) {
          return hybridResponse;
        }
        if (typeof input === "string" && input.includes("/api/index/search")) {
          return fallbackResponse;
        }
        throw new Error(`unexpected fetch ${input}`);
      })
      .mockName("fetch");
    vi.stubGlobal("fetch", fetchMock);

    const result = await runHybridSearch("example query");
    expect((result as HybridSearchResult).hits[0]?.url).toBe("https://example.com");
    expect(result.keywordFallback).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("posts to diagnostics endpoint and returns payload", async () => {
    const diagnosticsPayload = { ok: true, data: { job_id: "job-1" } };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(input).toContain("/api/diagnostics");
      expect(init?.method).toBe("POST");
      return new Response(JSON.stringify(diagnosticsPayload), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await triggerDiagnostics();
    expect(response.data?.job_id).toBe("job-1");
  });

  it("opens a progress stream for a job", () => {
    const events: string[] = [];
    class StubEventSource {
      url: string;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      constructor(url: string) {
        this.url = url;
        events.push(url);
      }
      close() {
        // noop
      }
      addEventListener() {
        // noop for test
      }
    }
    // @ts-expect-error - assigning test double
    global.EventSource = StubEventSource;

    const source = openProgressStream("job-123");
    expect(events[0]).toContain("/api/progress/job-123/stream");
    source.close();
  });
});
