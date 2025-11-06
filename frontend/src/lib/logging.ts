export type UIEvent = { event?: string; level?: string; msg?: string; meta?: Record<string, unknown> };

declare global {
  interface Window {
    appLogger?: { log: (payload: UIEvent) => void } | undefined;
  }
}

export async function sendUiLog(evt: UIEvent) {
  try {
    const payload = { ...evt, event: evt.event ?? 'ui.log', level: (evt.level ?? 'INFO').toUpperCase() };
    // Prefer Electron preload bridge if available
    if (typeof window !== 'undefined' && window.appLogger && typeof window.appLogger.log === 'function') {
      window.appLogger.log(payload);
      return;
    }
    const base = (process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_URL || 'http://127.0.0.1:5050').replace(/\/$/, '');
    await fetch(`${base}/api/logs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (error) {
    // Do not throw from logging
    // eslint-disable-next-line no-console
    console.warn('[sendUiLog] failed', error);
  }
}
