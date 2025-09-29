import { describe, expect, it } from "vitest";

import { resolveChatModelSelection } from "@/lib/chat-model";
import type { ConfiguredModels } from "@/lib/types";

describe("resolveChatModelSelection", () => {
  const configured: ConfiguredModels = {
    primary: "gpt-oss",
    fallback: "gemma3",
    embedder: "embeddinggemma",
  };

  it("prefers previous model when still available", () => {
    const result = resolveChatModelSelection({
      available: ["gpt-oss", "gemma3"],
      configured,
      stored: "gemma3",
      previous: "gemma3",
    });
    expect(result).toBe("gemma3");
  });

  it("falls back to stored value when previous is unavailable", () => {
    const result = resolveChatModelSelection({
      available: ["gpt-oss", "gemma3"],
      configured,
      stored: "gemma3",
      previous: "missing-model",
    });
    expect(result).toBe("gemma3");
  });

  it("returns configured primary when no stored value exists", () => {
    const result = resolveChatModelSelection({
      available: ["gpt-oss"],
      configured,
      stored: null,
      previous: null,
    });
    expect(result).toBe("gpt-oss");
  });

  it("returns null when nothing is available", () => {
    const result = resolveChatModelSelection({
      available: [],
      configured: { primary: null, fallback: null, embedder: null },
      stored: null,
      previous: null,
    });
    expect(result).toBeNull();
  });
});
