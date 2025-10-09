import { create } from 'zustand';

type NavStage = 'idle' | 'navigated' | 'loaded' | 'error';

export interface NavProgressEvent {
  stage: NavStage;
  url: string | null;
  status?: number | null;
  tabId?: number | null;
  timestamp: number;
}

interface NavProgressState {
  current: NavProgressEvent;
  history: NavProgressEvent[];
  setEvent: (event: Partial<NavProgressEvent>) => void;
  clear: () => void;
}

const initialEvent: NavProgressEvent = {
  stage: 'idle',
  url: null,
  status: null,
  tabId: null,
  timestamp: Date.now(),
};

export const useNavProgress = create<NavProgressState>((set) => ({
  current: initialEvent,
  history: [],
  setEvent: (event) =>
    set((state) => {
      const next: NavProgressEvent = {
        stage: event.stage ?? state.current.stage ?? 'idle',
        url: typeof event.url === 'string' ? event.url : state.current.url,
        status:
          typeof event.status === 'number'
            ? event.status
            : event.status === null
            ? null
            : state.current.status ?? null,
        tabId:
          typeof event.tabId === 'number'
            ? event.tabId
            : event.tabId === null
            ? null
            : state.current.tabId ?? null,
        timestamp: event.timestamp ?? Date.now(),
      };
      const history = [next, ...state.history].slice(0, 25);
      return {
        current: next,
        history,
      };
    }),
  clear: () => set({ current: initialEvent, history: [] }),
}));
