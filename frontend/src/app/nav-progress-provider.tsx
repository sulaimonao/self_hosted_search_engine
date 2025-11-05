'use client';

import { useEffect } from 'react';

import { useNavProgress } from '@/hooks/use-nav-progress';

interface NavProgressProviderProps {
  children: React.ReactNode;
}

export function NavProgressProvider({ children }: NavProgressProviderProps) {
  const setEvent = useNavProgress((state) => state.setEvent);
  const clear = useNavProgress((state) => state.clear);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const bridge = window.appBridge;
    if (!bridge?.onNavProgress) {
      return;
    }

    const unsubscribe = bridge.onNavProgress((raw) => {
      if (!raw || typeof raw !== 'object') {
        return;
      }
      const event = raw as { stage?: string; url?: string; status?: number; tabId?: number };
      const stage = typeof event.stage === 'string' ? event.stage.toLowerCase() : 'idle';
      const normalizedStage =
        stage === 'navigated' || stage === 'loaded' || stage === 'error' ? stage : 'idle';
      const url = typeof event.url === 'string' ? event.url : null;
      const status = typeof event.status === 'number' ? event.status : null;
      const tabId = typeof event.tabId === 'number' ? event.tabId : null;
      setEvent({ stage: normalizedStage, url, status, tabId, timestamp: Date.now() });
      if (normalizedStage === 'loaded') {
        // Reduce short-lived timeouts to avoid poll-storm signals; keep UX behavior identical
        window.setTimeout(() => {
          clear();
        }, 5000);
      }
    });

    return () => {
      if (typeof unsubscribe === 'function') {
        unsubscribe();
      }
    };
  }, [clear, setEvent]);

  return <>{children}</>;
}
