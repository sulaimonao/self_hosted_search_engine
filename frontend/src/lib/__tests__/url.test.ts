import { describe, expect, it } from "vitest";

import { normalizeAddressInput } from "@/lib/url";

describe("normalizeAddressInput", () => {
  it("returns https URLs unchanged", () => {
    const input = "https://example.com/path";
    expect(normalizeAddressInput(input)).toBe(input);
  });

  it("prepends https for domain-like inputs", () => {
    expect(normalizeAddressInput("example.com")).toBe("https://example.com");
  });

  it("treats whitespace as search query", () => {
    expect(normalizeAddressInput("   ")).toBe("https://www.google.com/search?igu=1");
  });

  it("uses Google search for queries", () => {
    expect(normalizeAddressInput("open ai")).toBe(
      "https://www.google.com/search?q=open+ai&igu=1",
    );
  });

  it("forces search mode when configured", () => {
    expect(normalizeAddressInput("example.com", { searchMode: "query" })).toBe(
      "https://www.google.com/search?q=example.com&igu=1",
    );
  });

  it("rewrites bare google.com to an embeddable start page", () => {
    expect(normalizeAddressInput("google.com")).toBe("https://www.google.com/webhp?igu=1");
  });

  it("adds igu flag for direct https google navigation", () => {
    expect(normalizeAddressInput("https://google.com")).toBe("https://www.google.com/webhp?igu=1");
  });
});
