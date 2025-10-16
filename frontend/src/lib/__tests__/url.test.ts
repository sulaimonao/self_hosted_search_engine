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
    expect(normalizeAddressInput("   ")).toBe("https://www.google.com/search?q=");
  });

  it("uses Google search for queries", () => {
    expect(normalizeAddressInput("open ai")).toBe("https://www.google.com/search?q=open%20ai");
  });

  it("forces search mode when configured", () => {
    expect(normalizeAddressInput("example.com", { searchMode: "query" })).toBe(
      "https://www.google.com/search?q=example.com",
    );
  });
});
