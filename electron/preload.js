const { contextBridge, ipcRenderer } = require('electron');

const ALLOWED_EVENTS = new Set([
  'system-check:open-panel',
  'system-check:initial-report',
  'system-check:initial-error',
  'system-check:report-missing',
  'system-check:report-error',
  'system-check:skipped',
]);

function subscribe(channel, handler) {
  if (!ALLOWED_EVENTS.has(channel) || typeof handler !== 'function') {
    return () => {};
  }
  const listener = (_event, payload) => {
    handler(payload);
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

contextBridge.exposeInMainWorld('desktop', {
  runSystemCheck: (options) => ipcRenderer.invoke('system-check:run', options ?? {}),
  getLastSystemCheck: () => ipcRenderer.invoke('system-check:last'),
  openSystemCheckReport: () => ipcRenderer.invoke('system-check:open-report'),
  exportSystemCheckReport: (options) => ipcRenderer.invoke('system-check:export-report', options ?? {}),
  onSystemCheckEvent: (channel, handler) => subscribe(channel, handler),
});
