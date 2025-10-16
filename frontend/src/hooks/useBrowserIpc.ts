"use client";

import { useEffect } from "react";

import {
  resolveBrowserAPI,
  subscribeNavState,
  subscribeTabList,
  type BrowserNavState,
  type BrowserTabList,
} from "@/lib/browser-ipc";
import { useAppStore } from "@/state/useAppStore";

function mapNavStateToTab(state: BrowserNavState) {
  return {
    title: state.title ?? state.url ?? "",
    url: state.url,
    favicon: state.favicon ?? null,
    canGoBack: state.canGoBack,
    canGoForward: state.canGoForward,
    isLoading: Boolean(state.isLoading),
    error: state.error ?? null,
  };
}

function applyTabList(summary: BrowserTabList | undefined) {
  if (!summary) {
    return;
  }
  useAppStore.getState().replaceTabs(summary);
}

export function useBrowserIpc() {
  useEffect(() => {
    const api = resolveBrowserAPI();
    if (!api) {
      return;
    }

    let cancelled = false;

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

    const unsubscribeTabs = subscribeTabList(api, (summary) => {
      applyTabList(summary);
    });

    const unsubscribeNav = subscribeNavState(api, (state) => {
      const patch = mapNavStateToTab(state);
      useAppStore.getState().updateTab(state.tabId, patch);
      if (state.isActive) {
        useAppStore.setState({ activeTabId: state.tabId });
      }
    });

    return () => {
      cancelled = true;
      unsubscribeTabs();
      unsubscribeNav();
    };
  }, []);
}
