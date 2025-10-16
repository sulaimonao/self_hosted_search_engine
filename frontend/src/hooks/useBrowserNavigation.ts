"use client";

import { useCallback, useMemo } from "react";
import { useShallow } from "zustand/react/shallow";

import { useAppStore } from "@/state/useAppStore";
import { resolveBrowserAPI } from "@/lib/browser-ipc";

export interface NavigateOptions {
  newTab?: boolean;
  title?: string;
  closePanel?: boolean;
}

export function useBrowserNavigation() {
  const { activeTab, addTab, updateTab, setActive, openPanel } = useAppStore(
    useShallow((state) => ({
      activeTab: state.activeTab?.(),
      addTab: state.addTab,
      updateTab: state.updateTab,
      setActive: state.setActive,
      openPanel: state.openPanel,
    })),
  );
  const browserAPI = useMemo(() => resolveBrowserAPI(), []);

  return useCallback(
    (url: string, options: NavigateOptions = {}): string | null => {
      const target = typeof url === "string" ? url.trim() : "";
      if (!target) {
        return null;
      }

      const normalizedTitle =
        typeof options.title === "string" && options.title.trim().length > 0
          ? options.title.trim()
          : undefined;

      if (options.closePanel) {
        openPanel(undefined);
      }

      if (browserAPI) {
        if (options.newTab || !activeTab) {
          void browserAPI
            .createTab(target)
            .catch((error) => console.warn("[browser] failed to open tab", error));
          return null;
        }
        browserAPI.navigate(target, { tabId: activeTab.id, transition: "link" });
        return activeTab.id;
      }

      if (options.newTab || !activeTab) {
        const id = addTab(target, normalizedTitle ?? target);
        if (normalizedTitle) {
          updateTab(id, { title: normalizedTitle });
        }
        setActive(id);
        return id;
      }

      updateTab(activeTab.id, {
        url: target,
        title: normalizedTitle ?? activeTab.title ?? target,
      });
      return activeTab.id;
    },
    [activeTab, addTab, browserAPI, openPanel, setActive, updateTab],
  );
}
