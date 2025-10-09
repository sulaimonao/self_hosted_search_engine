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
    const bridge = (window as unknown as {
      appBridge?: {
        onNavProgress?: (callback: (event: unknown) => void) => () => void;
      };
    }).appBridge;
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
        window.setTimeout(() => {
          clear();
        }, 2200);
      }
    });

    return () => {
      unsubscribe?.();
    };
  }, [setEvent]);

  return <>{children}</>;
}
