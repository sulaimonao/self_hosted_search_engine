import { describe, expect, it } from "vitest";
import { buildResolvedPageContext, countWords } from "@/lib/pageContext";

describe("page context helper", () => {
  it("returns a null payload snapshot when no context is available", () => {
    const snapshot = buildResolvedPageContext({});
    expect(snapshot.contextMessage).toBeNull();
    expect(snapshot.contextPayload).toBeNull();
    expect(snapshot.selectionText).toBeNull();
    expect(snapshot.pageUrl).toBeNull();
    expect(snapshot.pageTitle).toBeNull();
  });

  it("builds a context payload with fallback metadata", () => {
    const contextData = {
      url: "https://example.com",
      summary: "hello world",
      selection: { text: "snippet", word_count: 1 },
      metadata: { title: "metadata title" },
      history: [{ id: 1 }],
      memories: [{ name: "memo" }],
    };
    const snapshot = buildResolvedPageContext({
      contextData,
      fallbackTitle: "tab title",
      browserTitle: "browser title",
    });
    expect(snapshot.contextPayload).not.toBeNull();
    expect(snapshot.contextPayload?.url).toBe("https://example.com");
    // fallbackTitle should take precedence over metadata/browser titles
    expect(snapshot.contextPayload?.title).toBe("tab title");
    expect(snapshot.contextPayload?.summary).toBe("hello world");
    expect(snapshot.contextPayload?.metadata).toEqual({ title: "metadata title" });
    expect(snapshot.contextMessage?.role).toBe("system");
    expect(snapshot.contextMessage?.content).toContain("\"context\"");
  });

  it("computes selection word counts when the backend omits them", () => {
    const snapshot = buildResolvedPageContext({
      contextData: {
        summary: null,
        metadata: null,
        selection: undefined,
        history: undefined,
        memories: undefined,
      },
      fallbackUrl: "https://docs.local",
      selectionText: "some custom selection",
    });
    expect(snapshot.selectionWordCount).toBe(countWords("some custom selection"));
    expect(snapshot.contextPayload?.selection_word_count).toBe(countWords("some custom selection"));
  });
});
