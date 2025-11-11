import { mkdtempSync, rmSync } from "fs";
import { tmpdir } from "os";
import path from "path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  initializeBrowserData,
  HISTORY_MAX_ENTRIES,
  DOWNLOAD_MAX_ENTRIES,
} from "./browser-data";

const DAY_MS = 24 * 60 * 60 * 1000;

function createStore() {
  const tempDir = mkdtempSync(path.join(tmpdir(), "browser-data-test-"));
  const store = initializeBrowserData({
    getPath: () => tempDir,
  });
  return { tempDir, store };
}

describe("BrowserDataStore retention", () => {
  let tempDir: string;
  let store: any;

  beforeEach(() => {
    const result = createStore();
    tempDir = result.tempDir;
    store = result.store;
  });

  afterEach(() => {
    store?.db?.close?.();
    rmSync(tempDir, { recursive: true, force: true });
  });

  it("drops history entries older than 30 days when new entries arrive", () => {
    const oldEntry = store.recordNavigation({
      url: "https://example.com/old",
      title: "Old entry",
      transition: "link",
      referrer: null,
    });
    const staleTimestamp = Date.now() - 31 * DAY_MS;
    store.db
      .prepare("UPDATE history SET visit_time=? WHERE id=?")
      .run(staleTimestamp, oldEntry.id);

    store.recordNavigation({ url: "https://example.com/new", title: "Fresh" });
    const recentEntries = store.getRecentHistory(10);

    expect(recentEntries.some((entry) => entry.id === oldEntry.id)).toBe(false);
  });

  it("enforces an upper bound on stored history entries", () => {
    vi.useFakeTimers();
    const base = Date.now();
    try {
      for (let idx = 0; idx < HISTORY_MAX_ENTRIES + 25; idx += 1) {
        vi.setSystemTime(base + idx * 10);
        store.recordNavigation({
          url: `https://example.com/page-${idx}`,
          title: `Page ${idx}`,
        });
      }
    } finally {
      vi.useRealTimers();
    }

    const entries = store.getRecentHistory(HISTORY_MAX_ENTRIES + 50);
    expect(entries).toHaveLength(HISTORY_MAX_ENTRIES);
    expect(entries.some((entry) => entry.url === "https://example.com/page-0")).toBe(false);
    expect(entries.some((entry) => entry.url === `https://example.com/page-${HISTORY_MAX_ENTRIES + 24}`)).toBe(true);
    expect(entries[entries.length - 1].url).toBe("https://example.com/page-25");
  });

  it("trims downloads by age and count", () => {
    vi.useFakeTimers();
    const base = Date.now();
    try {
      store.recordDownload({
        id: "old-download",
        url: "https://example.com/old.bin",
        filename: "old.bin",
        bytesTotal: 10,
        bytesReceived: 10,
        path: "/tmp/old.bin",
        state: "completed",
        completedAt: Date.now(),
      });
      const staleTimestamp = base - 31 * DAY_MS;
      store.db
        .prepare("UPDATE downloads SET started_at=? WHERE id=?")
        .run(staleTimestamp, "old-download");

      for (let idx = 0; idx < DOWNLOAD_MAX_ENTRIES; idx += 1) {
        vi.setSystemTime(base + idx * 10);
        store.recordDownload({
          id: `dl-${idx}`,
          url: `https://example.com/file-${idx}.bin`,
          filename: `file-${idx}.bin`,
          bytesTotal: idx,
          bytesReceived: idx,
          path: `/tmp/file-${idx}.bin`,
          state: "completed",
          completedAt: Date.now(),
        });
      }
    } finally {
      vi.useRealTimers();
    }

    const downloads = store.listDownloads(DOWNLOAD_MAX_ENTRIES + 10);
    expect(downloads).toHaveLength(DOWNLOAD_MAX_ENTRIES);
    expect(downloads.some((entry) => entry.id === "old-download")).toBe(false);
    expect(downloads[0].id).toBe(`dl-${DOWNLOAD_MAX_ENTRIES - 1}`);
    expect(downloads[downloads.length - 1].id).toBe("dl-0");
  });

  it("clears history and downloads via helper methods", () => {
    store.recordNavigation({ url: "https://example.com/a", title: "A" });
    store.recordNavigation({ url: "https://example.com/b", title: "B" });
    store.recordDownload({
      id: "clear-me",
      url: "https://example.com/clear.bin",
      filename: "clear.bin",
      bytesTotal: 1,
      bytesReceived: 1,
      path: "/tmp/clear.bin",
      state: "completed",
      completedAt: Date.now(),
    });

    store.clearHistory();
    store.clearDownloads();

    expect(store.getRecentHistory(10)).toEqual([]);
    expect(store.listDownloads(10)).toEqual([]);
  });
});
