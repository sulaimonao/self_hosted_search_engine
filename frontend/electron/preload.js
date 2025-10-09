import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('appBridge', {
  onNavProgress: (callback) => {
    if (typeof callback !== 'function') {
      return () => {};
    }
    const listener = (_event, data) => {
      try {
        callback(data);
      } catch (error) {
        console.warn('nav-progress listener failed', error);
      }
    };
    ipcRenderer.on('nav-progress', listener);
    return () => ipcRenderer.removeListener('nav-progress', listener);
  },
});
