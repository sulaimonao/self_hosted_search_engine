import { describe, expect, it, vi } from "vitest";

import {
  collectUniqueHttpCitations,
  indexCitationUrls,
  type CitationIndexStatus,
} from "@/components/app-shell";

describe("collectUniqueHttpCitations", () => {
  it("filters to unique HTTP(S) URLs", () => {
    const result = collectUniqueHttpCitations([
      " https://example.com/path ",
      "https://example.com/path",
      "http://example.com/other",
      "ftp://ignored.example", // ignored
      "",
      null,
      undefined,
      42,
    ]);

    expect(result).toEqual([
      "https://example.com/path",
      "http://example.com/other",
    ]);
  });
});

describe("indexCitationUrls", () => {
  const createOptions = () => {
    const queueShadowIndex = vi.fn().mockResolvedValue(undefined);
    const handleQueueAdd = vi.fn().mockResolvedValue(undefined);
    const setStatus = vi.fn<
      (url: string, status: CitationIndexStatus, error?: string | null) => void
    >();
    const appendLog = vi.fn();
    const pushToast = vi.fn();

    return { queueShadowIndex, handleQueueAdd, setStatus, appendLog, pushToast };
  };

  it("queues through shadow indexing when enabled", async () => {
    const { queueShadowIndex, handleQueueAdd, setStatus, appendLog, pushToast } =
      createOptions();

    await indexCitationUrls(["https://example.com/a", "https://example.com/b"], {
      shadowModeEnabled: true,
      queueShadowIndex,
      handleQueueAdd,
      setStatus,
      appendLog,
      pushToast,
    });

    expect(queueShadowIndex).toHaveBeenCalledTimes(2);
    expect(handleQueueAdd).not.toHaveBeenCalled();
    expect(setStatus.mock.calls).toEqual([
      ["https://example.com/a", "loading"],
      ["https://example.com/a", "success"],
      ["https://example.com/b", "loading"],
      ["https://example.com/b", "success"],
    ]);
    expect(appendLog).not.toHaveBeenCalled();
    expect(pushToast).not.toHaveBeenCalled();
  });

  it("falls back to crawl queue when shadow mode is disabled", async () => {
    const { queueShadowIndex, handleQueueAdd, setStatus } = createOptions();

    await indexCitationUrls(["https://example.com/a"], {
      shadowModeEnabled: false,
      queueShadowIndex,
      handleQueueAdd,
      setStatus,
      appendLog: vi.fn(),
      pushToast: vi.fn(),
    });

    expect(queueShadowIndex).not.toHaveBeenCalled();
    expect(handleQueueAdd).toHaveBeenCalledWith(
      "https://example.com/a",
      "page",
      "Auto-indexed from chat citation",
    );
  });

  it("surfaces errors through logs and toasts", async () => {
    const error = new Error("boom");
    const { queueShadowIndex, handleQueueAdd, setStatus, appendLog, pushToast } =
      createOptions();
    queueShadowIndex.mockRejectedValueOnce(error);

    await indexCitationUrls(["https://example.com/a"], {
      shadowModeEnabled: true,
      queueShadowIndex,
      handleQueueAdd,
      setStatus,
      appendLog,
      pushToast,
    });

    expect(setStatus.mock.calls).toEqual([
      ["https://example.com/a", "loading"],
      ["https://example.com/a", "error", "boom"],
    ]);
    expect(appendLog).toHaveBeenCalledWith(
      expect.objectContaining({
        label: "Citation indexing failed",
        detail: expect.stringContaining("https://example.com/a: boom"),
        status: "error",
      }),
    );
    expect(pushToast).toHaveBeenCalledWith("boom", { variant: "destructive" });
  });
});
