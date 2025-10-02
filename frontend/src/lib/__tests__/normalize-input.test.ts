import { describe, expect, it } from "vitest";

import { normalizeInput } from "../normalize-input";

describe("normalizeInput", () => {
  it("treats bare domains as external urls", () => {
    expect(normalizeInput("youtube.com/watch?v=dQw4w9WgXcQ")).toEqual({
      kind: "external",
      urlOrPath: "https://youtube.com/watch?v=dQw4w9WgXcQ",
    });
  });

  it("auto-prefixes https for domain paths", () => {
    expect(normalizeInput("example.org/docs")).toEqual({
      kind: "external",
      urlOrPath: "https://example.org/docs",
    });
  });

  it("passes through absolute https urls", () => {
    expect(normalizeInput("  https://news.ycombinator.com ")).toEqual({
      kind: "external",
      urlOrPath: "https://news.ycombinator.com",
    });
  });

  it("routes plain phrases to internal search", () => {
    expect(normalizeInput("rust async channels")).toEqual({
      kind: "internal",
      urlOrPath: "/search?q=rust%20async%20channels",
    });
  });
});
