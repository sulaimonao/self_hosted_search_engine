import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchModelInventory, sendChat, ChatRequestError } from "@/lib/api";
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
            chat_models: ["gpt-oss", "gemma3"],
            available: ["gpt-oss", "gemma3", "embeddinggemma"],
            configured: {
              primary: "gpt-oss",
              fallback: "gemma3",
            },
            embedder: "embeddinggemma",
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
    expect(inventory.chatModels).toEqual(["gpt-oss", "gemma3"]);
    expect(inventory.configured.primary).toBe("gpt-oss");
    expect(inventory.status.running).toBe(true);
    expect(inventory.models[0].model).toBe("gpt-oss");
  });
});

describe("sendChat", () => {
  it("sends the selected model and returns trace info", async () => {
    const history: ChatMessage[] = [];
    const response = new Response(
      JSON.stringify({
        reasoning: "Because",
        answer: "Hi!",
        citations: ["https://example.com"],
        model: "gemma3",
        trace_id: "req_test",
      }),
      {
        status: 200,
        headers: {
          "X-Request-Id": "req_test",
          "X-LLM-Model": "gemma3",
        },
      },
    );

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = init?.body as string;
      const payload = JSON.parse(body);
      expect(payload.model).toBe("gpt-oss");
      expect(payload.url).toBe("https://example.com");
      return response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await sendChat(history, "hi", {
      model: "gpt-oss",
      url: "https://example.com",
    });

    expect(result.traceId).toBe("req_test");
    expect(result.model).toBe("gemma3");
    expect(result.payload.answer).toBe("Hi!");
    expect(result.payload.reasoning).toBe("Because");
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
      sendChat([], "hi", { model: "gpt-oss" }),
    ).rejects.toMatchObject({
      traceId: "req_fail",
      hint: "ollama pull gpt-oss",
      code: "model_not_found",
    } satisfies Partial<ChatRequestError>);
  });
});
