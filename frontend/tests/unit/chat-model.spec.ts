import { describe, it, expect } from "vitest";
import { resolveChatModelSelection } from "../../src/lib/chat-model";

describe("resolveChatModelSelection", () => {
  it("prefers previous selection when available", () => {
    const selected = resolveChatModelSelection({
      available: ["gemma3:1", "gpt-oss:120b"],
      configured: { primary: "gemma3", fallback: "gpt-oss", embedder: null },
      stored: null,
      previous: "gpt-oss:120b",
    });
    expect(selected).toBe("gpt-oss:120b");
  });

  it("falls back to configured primary when stored/previous not available but primary family matches", () => {
    const selected = resolveChatModelSelection({
      available: ["gemma3:1", "gpt-oss:120b"],
      configured: { primary: "gemma3", fallback: "gpt-oss", embedder: null },
      stored: null,
      previous: null,
    });
    expect(selected).toBe("gemma3:1");
  });

  it("returns null when nothing is available and no configured primary", () => {
    const selected = resolveChatModelSelection({
      available: [],
      configured: { primary: null, fallback: null, embedder: null },
      stored: null,
      previous: null,
    });
    expect(selected).toBeNull();
  });
});
