import { create } from "zustand";

type Mode = "search" | "browser";

export type FeatureName = "llm" | "serverTime";
export type FeatureStatus = "unknown" | "available" | "unavailable";

interface AppState {
  mode: Mode;
  shadow: boolean;
  autopilot: boolean;
  selectedModel: string | null;
  availableModels: string[];
  features: Record<FeatureName, FeatureStatus>;
  setMode: (mode: Mode) => void;
  setShadow: (value: boolean) => void;
  toggleShadow: () => void;
  setAutopilot: (value: boolean) => void;
  toggleAutopilot: () => void;
  setSelectedModel: (model: string | null) => void;
  setAvailableModels: (models: string[]) => void;
  setFeature: (name: FeatureName, status: FeatureStatus) => void;
}

const INITIAL_FEATURES: Record<FeatureName, FeatureStatus> = {
  llm: "unknown",
  serverTime: "unknown",
};

export const useApp = create<AppState>((set) => ({
  mode: "search",
  shadow: false,
  autopilot: false,
  selectedModel: null,
  availableModels: [],
  features: INITIAL_FEATURES,
  setMode: (mode) => set({ mode }),
  setShadow: (value) => set({ shadow: value }),
  toggleShadow: () =>
    set((state) => ({
      shadow: !state.shadow,
    })),
  setAutopilot: (value) => set({ autopilot: value }),
  toggleAutopilot: () =>
    set((state) => ({
      autopilot: !state.autopilot,
    })),
  setSelectedModel: (model) => set({ selectedModel: model }),
  setAvailableModels: (models) => set({ availableModels: models }),
  setFeature: (name, status) =>
    set((state) => ({
      features: { ...state.features, [name]: status },
    })),
}));
