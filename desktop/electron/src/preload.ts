import { contextBridge, ipcRenderer } from "electron";

type FallbackPayload = { url: string };

type FallbackHandler = (payload: FallbackPayload) => void;

declare global {
  interface Window {
    omni?: {
      openUrl: (url: string) => Promise<void>;
      pickDir: () => Promise<string | null>;
      onViewerFallback: (handler: FallbackHandler) => (() => void) | void;
      quit: () => Promise<void>;
    };
  }
}

contextBridge.exposeInMainWorld("omni", {
  openUrl: (url: string) => ipcRenderer.invoke("open-url", url),
  pickDir: () => ipcRenderer.invoke("pick-dir"),
  onViewerFallback: (handler: FallbackHandler) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: FallbackPayload) => {
      handler(payload);
    };
    ipcRenderer.on("viewer-fallback", listener);
    return () => {
      ipcRenderer.removeListener("viewer-fallback", listener);
    };
  },
  quit: () => ipcRenderer.invoke("quit"),
});
