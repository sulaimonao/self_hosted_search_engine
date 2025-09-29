import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchModelInventory, streamChat, ChatRequestError } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("fetchModelInventory", () => {
  it("parses available models and configuration", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (typeof input === "string" && input.includes("/api/llm/models")) {
        return new Response(
          JSON.stringify({
            available: ["gpt-oss", "gemma3"],
            configured: {
              primary: "gpt-oss",
              fallback: "gemma3",
              embedder: "embeddinggemma",
            },
            ollama_host: "http://127.0.0.1:11434",
          }),
          { status: 200 },
        );
      }
      if (typeof input === "string" && input.includes("/api/llm/health")) {
        return new Response(
          JSON.stringify({ reachable: true, model_count: 2, duration_ms: 5 }),
          { status: 200 },
        );
      }
      throw new Error(`Unexpected fetch ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const inventory = await fetchModelInventory();
    expect(inventory.available).toEqual(["gpt-oss", "gemma3"]);
    expect(inventory.configured.primary).toBe("gpt-oss");
    expect(inventory.status.running).toBe(true);
    expect(inventory.models[0].model).toBe("gpt-oss");
  });
});

describe("streamChat", () => {
  it("sends the selected model and returns trace info", async () => {
    const history: ChatMessage[] = [];
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: {"type":"done"}\n\n'));
        controller.close();
      },
    });
    const response = new Response(stream, {
      status: 200,
      headers: {
        "X-Request-Id": "req_test",
        "X-LLM-Model": "gemma3",
      },
    });

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body as string;
      const payload = JSON.parse(body);
      expect(payload.model).toBe("gpt-oss");
      return response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const events: string[] = [];
    const result = await streamChat(history, "hi", {
      model: "gpt-oss",
      onEvent: (chunk) => {
        if (chunk.type === "done") {
          events.push("done");
        }
      },
    });

    expect(events).toContain("done");
    expect(result.traceId).toBe("req_test");
    expect(result.model).toBe("gemma3");
  });

  it("throws ChatRequestError with metadata when upstream fails", async () => {
    const errorResponse = new Response(
      JSON.stringify({ error: "model_not_found", hint: "ollama pull gpt-oss" }),
      {
        status: 503,
        headers: { "X-Request-Id": "req_fail" },
      },
    );
    const fetchMock = vi.fn(async () => errorResponse);
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      streamChat([], "hi", { model: "gpt-oss", onEvent: () => {} }),
    ).rejects.toMatchObject({
      traceId: "req_fail",
      hint: "ollama pull gpt-oss",
      code: "model_not_found",
    } satisfies Partial<ChatRequestError>);
  });
});
