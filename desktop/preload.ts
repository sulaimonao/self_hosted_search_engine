import { contextBridge, ipcRenderer } from 'electron';

type ShadowSnapshot = {
  url: string;
  html?: string;
  text?: string;
  screenshot_b64?: string;
  headers?: Record<string, string>;
  dom_hash?: string;
  outlinks?: { url: string; same_site?: boolean }[];
  policy_id?: string;
  tab_id?: string;
  session_id?: string;
};

contextBridge.exposeInMainWorld('DesktopBridge', {
  shadowCapture: (payload: ShadowSnapshot) => ipcRenderer.invoke('shadow:capture', payload),
  indexSearch: (q: string) => ipcRenderer.invoke('index:search', q),
  onShadowToggle: (cb: () => void) => {
    const listener = () => cb();
    ipcRenderer.on('shadow/toggle', listener);
    return () => ipcRenderer.off('shadow/toggle', listener);
  },
});
