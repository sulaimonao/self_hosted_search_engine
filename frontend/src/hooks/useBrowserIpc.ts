"use client";

import { useEffect, useRef } from "react";

import {
  resolveBrowserAPI,
  subscribeNavState,
  subscribeTabList,
  subscribeHistory,
  subscribeDownloads,
  subscribePermissionPrompts,
  subscribePermissionState,
  subscribeSettings,
  type BrowserNavState,
  type BrowserTabList,
} from "@/lib/browser-ipc";
import { useAppStore } from "@/state/useAppStore";
import { useBrowserRuntimeStore } from "@/state/useBrowserRuntime";
import { setIfChanged } from "@/lib/store/utils";
import { apiClient } from "@/lib/backend/apiClient";

function mapNavStateToTab(state: BrowserNavState) {
  return {
    title: state.title ?? state.url ?? "",
    url: state.url,
    favicon: state.favicon ?? null,
    canGoBack: state.canGoBack,
    canGoForward: state.canGoForward,
    isLoading: Boolean(state.isLoading),
    error: state.error ?? null,
    sessionPartition: state.sessionPartition ?? "persist:main",
    incognito: Boolean(state.isIncognito),
  };
}

function applyTabList(summary: BrowserTabList | undefined) {
  if (!summary) {
    return;
  }
  useAppStore.getState().replaceTabs(summary);
}

const guardedAppSetState = setIfChanged(useAppStore.setState, useAppStore.getState);

export function useBrowserIpc() {
  useEffect(() => {
    const api = resolveBrowserAPI();
    if (!api) {
      return;
    }

    let cancelled = false;
    const persistedHistory = new Set<string>();

    const persistHistory = async (entry: BrowserHistoryEntry) => {
      if (!entry?.url) return;
      const key = `${entry.id ?? entry.url}|${entry.visitTime ?? 0}`;
      if (persistedHistory.has(key)) {
        return;
      }
      persistedHistory.add(key);
      try {
        await apiClient.post("/api/history/visit", {
          url: entry.url,
          title: entry.title,
          visited_at: entry.visitTime ? new Date(entry.visitTime).toISOString() : undefined,
          tab_id: entry.tabId,
          referrer: entry.referrer,
        });
      } catch (error) {
        console.warn("[browser] failed to persist history", error);
      }
      try {
        await apiClient.post("/api/research/page", {
          url: entry.url,
          title: entry.title,
          source: "navigation",
        });
      } catch (error) {
        console.debug?.("[browser] enqueue crawl skipped", error);
      }
    };

    api
      .requestTabList()
      .then((summary) => {
        if (!cancelled) {
          applyTabList(summary);
        }
      })
      .catch((error) => {
        console.warn("[browser] failed to load initial tab list", error);
      });

    api
      .getSettings()
      .then((settings) => {
        if (!cancelled && settings) {
          useBrowserRuntimeStore.getState().setSettings(settings);
        }
      })
      .catch((error) => console.warn("[browser] failed to load settings", error));

    api
      .requestHistory(100)
      .then((entries) => {
        if (!cancelled && Array.isArray(entries)) {
          useBrowserRuntimeStore.getState().setHistory(entries);
        }
      })
      .catch((error) => console.warn("[browser] failed to load history", error));

    api
      .requestDownloads(25)
      .then((entries) => {
        if (!cancelled && Array.isArray(entries)) {
          const store = useBrowserRuntimeStore.getState();
          entries.forEach((entry) => store.upsertDownload(entry));
        }
      })
      .catch((error) => console.warn("[browser] failed to load downloads", error));

    const unsubscribeTabs = subscribeTabList(api, (summary) => {
      applyTabList(summary);
    });

    const unsubscribeNav = subscribeNavState(api, (state) => {
      const patch = mapNavStateToTab(state);
      const store = useAppStore.getState();
      store.updateTab(state.tabId, patch);
      if (state.isActive) {
        guardedAppSetState({ activeTabId: state.tabId });
        if (typeof state.url === "string" && state.url.trim().length > 0) {
          store.setBrowserDesiredUrl(state.url);
        }
      }
    });

    const unsubscribeHistory = subscribeHistory(api, (entry) => {
      useBrowserRuntimeStore.getState().addHistory(entry);
      void persistHistory(entry);
    });

    const unsubscribeDownloads = subscribeDownloads(api, (download) => {
      useBrowserRuntimeStore.getState().upsertDownload(download);
    });

    const unsubscribeSettings = subscribeSettings(api, (settings) => {
      useBrowserRuntimeStore.getState().setSettings(settings);
    });

    const unsubscribePrompts = subscribePermissionPrompts(api, (prompt) => {
      useBrowserRuntimeStore.getState().setPermissionPrompt(prompt);
    });

    const unsubscribePermissionState = subscribePermissionState(api, (state) => {
      useBrowserRuntimeStore.getState().updatePermissions(state);
    });

    return () => {
      cancelled = true;
      unsubscribeTabs();
      unsubscribeNav();
      unsubscribeHistory();
      unsubscribeDownloads();
      unsubscribeSettings();
      unsubscribePrompts();
      unsubscribePermissionState();
    };
  }, []);
}
