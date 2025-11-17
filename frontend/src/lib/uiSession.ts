import { safeSessionStorage } from "@/utils/isomorphicStorage";

export const UI_SESSION_KEYS = {
  aiPanelOpen: "ui.ai-panel.open",
  aiPanelTab: "ui.ai-panel.tab",
} as const;

export function setAiPanelSessionOpen(value: boolean) {
  safeSessionStorage.set(UI_SESSION_KEYS.aiPanelOpen, JSON.stringify(value));
}
