import { describe, it, expect, vi } from "vitest";

import { chatClient } from "../../src/lib/chatClient";

const ORIGINAL_FETCH = global.fetch;

describe("ChatClient fallback behavior", () => {
  it("logs a breadcrumb and retries without stream when streaming fails", async () => {
    const debugLines: string[] = [];
    const consoleSpy = vi.spyOn(console, "debug").mockImplementation((...args: unknown[]) => {
      const text = args.map(String).join(" ");
      debugLines.push(text);
    });

    const jsonResponse = new Response(
      JSON.stringify({ reasoning: "", answer: "Hello", citations: [], model: "gemma3", trace_id: "x" }),
      { status: 200, headers: { "Content-Type": "application/json", "X-Request-Id": "x" } },
    );

    const fetchMock = vi
      .fn<Parameters<typeof fetch>, ReturnType<typeof fetch>>()
      // First call simulates a network failure for streaming
      .mockImplementationOnce(() => {
        throw new TypeError("network down");
      })
      // Second call returns a successful JSON response
      .mockResolvedValueOnce(jsonResponse);
    vi.stubGlobal("fetch", fetchMock);

    const result = await chatClient.send({ messages: [{ role: "user", content: "hi" }], model: "gemma3" });
    expect(result.payload.answer).toBe("Hello");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Ensure we logged the fallback breadcrumb
    const sawBreadcrumb = debugLines.some((line) => line.includes("[chat] streaming failed; retrying without stream"));
    expect(sawBreadcrumb).toBe(true);

    consoleSpy.mockRestore();
    global.fetch = ORIGINAL_FETCH;
  });
});
