'use client';

import { Loader2 } from 'lucide-react';

import { useNavProgress } from '@/hooks/use-nav-progress';

export function NavProgressHud() {
  const event = useNavProgress((state) => state.current);

  if (!event || event.stage === 'idle') {
    return null;
  }

  const stageLabel = (() => {
    switch (event.stage) {
      case 'navigated':
        return 'Navigating';
      case 'loaded':
        return event.status && event.status >= 400 ? 'Load failed' : 'Loaded';
      case 'error':
        return 'Navigation error';
      default:
        return 'Idle';
    }
  })();

  return (
    <div className="sticky top-0 z-40 flex items-center justify-between gap-3 border-b bg-muted/80 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
      <div className="flex items-center gap-2 truncate">
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        <span className="font-medium text-foreground">{stageLabel}</span>
        {event.url ? (
          <span className="truncate" title={event.url}>
            {event.url}
          </span>
        ) : null}
        {typeof event.tabId === 'number' ? (
          <span className="rounded border px-1 text-[10px] font-semibold">tab {event.tabId}</span>
        ) : null}
      </div>
      {typeof event.status === 'number' ? (
        <span className="font-medium text-foreground">{event.status}</span>
      ) : null}
    </div>
  );
}
