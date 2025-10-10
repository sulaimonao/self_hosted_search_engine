const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('desktop', {
  // Placeholder for future IPC surface
});
