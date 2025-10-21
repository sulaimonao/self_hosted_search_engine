import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { chatClient } from "@/lib/chatClient";
import type { ChatSendRequest } from "@/lib/chatClient";
import type { ChatStreamEvent } from "@/lib/types";

const ORIGINAL_FETCH = global.fetch;

describe("ChatClient", () => {
  beforeEach(() => {
    global.fetch = ORIGINAL_FETCH;
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.restoreAllMocks();
  });

  it("parses streaming NDJSON events and surfaces metadata", async () => {
    const events: ChatStreamEvent[] = [];
    const streamBody = [
      JSON.stringify({ type: "metadata", attempt: 1, model: "gemma3", trace_id: "stream-1" }),
      JSON.stringify({ type: "delta", answer: "Hello" }),
      JSON.stringify({
        type: "complete",
        payload: {
          reasoning: "Because",
          answer: "Hello",
          citations: [],
          model: "gemma3",
          trace_id: "stream-1",
        },
      }),
      "",
    ].join("\n");
    const response = new Response(streamBody, {
      status: 200,
      headers: {
        "Content-Type": "application/x-ndjson",
        "X-Request-Id": "stream-1",
      },
    });

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(JSON.parse(init?.body as string).stream).toBe(true);
      return response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const request: ChatSendRequest = {
      messages: [{ role: "user", content: "hi" }],
      model: "gemma3",
      onEvent: (event) => events.push(event),
    };
    const result = await chatClient.send(request);

    expect(events.some((event) => event.type === "delta")).toBe(true);
    expect(result.traceId).toBe("stream-1");
    expect(result.model).toBe("gemma3");
    expect(result.payload.answer).toBe("Hello");
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("retries with stream disabled when the streaming request fails", async () => {
    const jsonResponse = new Response(
      JSON.stringify({
        reasoning: "Fallback",
        answer: "Hi",
        citations: [],
        model: "gemma3",
        trace_id: "fallback-1",
      }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "X-Request-Id": "fallback-1",
        },
      },
    );

    const fetchMock = vi
      .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
      .mockImplementationOnce(() => {
        throw new TypeError("stream failed");
      })
      .mockResolvedValueOnce(jsonResponse);
    vi.stubGlobal("fetch", fetchMock);

    const result = await chatClient.send({ messages: [{ role: "user", content: "hi" }], model: "gemma3" });

    expect(result.payload.answer).toBe("Hi");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const firstCall = fetchMock.mock.calls[0];
    const secondCall = fetchMock.mock.calls[1];
    expect(JSON.parse((firstCall?.[1]?.body as string) ?? "{}").stream).toBe(true);
    expect(JSON.parse((secondCall?.[1]?.body as string) ?? "{}").stream).toBe(false);
  });
});
