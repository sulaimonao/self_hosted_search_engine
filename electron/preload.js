const { contextBridge, ipcRenderer } = require('electron');

const ALLOWED_EVENTS = new Set([
  'system-check:open-panel',
  'system-check:initial-report',
  'system-check:initial-error',
  'system-check:report-missing',
  'system-check:report-error',
  'system-check:skipped',
]);

const BROWSER_ALLOWED_CHANNELS = new Set([
  'nav:state',
  'browser:tabs',
  'history:append',
  'downloads:update',
  'permissions:prompt',
  'permissions:state',
  'settings:state',
]);

const NOOP_UNSUBSCRIBE = () => {};

function subscribe(channel, handler) {
  if (!ALLOWED_EVENTS.has(channel) || typeof handler !== 'function') {
    return NOOP_UNSUBSCRIBE;
  }
  const listener = (_event, payload) => {
    try {
      handler(payload);
    } catch (error) {
      console.warn('[desktop] system check handler threw', error);
    }
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

function subscribeBrowserChannel(channel, handler) {
  if (!BROWSER_ALLOWED_CHANNELS.has(channel) || typeof handler !== 'function') {
    return NOOP_UNSUBSCRIBE;
  }
  const listener = (_event, payload) => {
    try {
      handler(payload);
    } catch (error) {
      console.warn(`[desktop] browser channel handler threw for ${channel}`, error);
    }
  };
  ipcRenderer.on(channel, listener);
  return () => {
    ipcRenderer.removeListener(channel, listener);
  };
}

function spoofNavigator() {
  try {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.webdriver', error);
  }

  try {
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.languages', error);
  }

  try {
    class FakePluginArray extends Array {
      item(index) {
        return this[index] ?? null;
      }

      namedItem(name) {
        return this.find((plugin) => plugin && plugin.name === name) ?? null;
      }

      refresh() {}
    }

    const fakePlugins = new FakePluginArray(
      { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
    );

    Object.freeze(fakePlugins);

    Object.defineProperty(navigator, 'plugins', {
      get: () => fakePlugins,
    });
  } catch (error) {
    console.warn('[preload] failed to patch navigator.plugins', error);
  }
}

function createBrowserAPI() {
  return {
    navigate: (url, options) => {
      const target = typeof url === 'string' ? url.trim() : '';
      if (!target) {
        return;
      }
      ipcRenderer.send('nav:navigate', {
        url: target,
        tabId: options?.tabId ?? null,
        transition: options?.transition,
      });
    },
    back: (options) => {
      ipcRenderer.send('nav:back', {
        tabId: options?.tabId ?? null,
      });
    },
    forward: (options) => {
      ipcRenderer.send('nav:forward', {
        tabId: options?.tabId ?? null,
      });
    },
    goBack: (options) => {
      ipcRenderer.send('nav:back', {
        tabId: options?.tabId ?? null,
      });
    },
    goForward: (options) => {
      ipcRenderer.send('nav:forward', {
        tabId: options?.tabId ?? null,
      });
    },
    reload: (options) => {
      ipcRenderer.send('nav:reload', {
        tabId: options?.tabId ?? null,
        ignoreCache: options?.ignoreCache ?? false,
      });
    },
    createTab: (url) => ipcRenderer.invoke('browser:create-tab', { url }),
    closeTab: (tabId) => ipcRenderer.invoke('browser:close-tab', { tabId }),
    setActiveTab: (tabId) => {
      if (typeof tabId === 'string' && tabId) {
        ipcRenderer.send('browser:set-active', tabId);
      }
    },
    setBounds: (bounds) => {
      if (!bounds || typeof bounds !== 'object') {
        return;
      }
      const payload = {
        x: Number.isFinite(bounds.x) ? Number(bounds.x) : 0,
        y: Number.isFinite(bounds.y) ? Number(bounds.y) : 0,
        width: Number.isFinite(bounds.width) ? Number(bounds.width) : 0,
        height: Number.isFinite(bounds.height) ? Number(bounds.height) : 0,
      };
      ipcRenderer.send('browser:bounds', payload);
    },
    onState: (handler) => subscribeBrowserChannel('nav:state', handler),
    onNavState: (handler) => subscribeBrowserChannel('nav:state', handler),
    onTabList: (handler) => subscribeBrowserChannel('browser:tabs', handler),
    onHistoryEntry: (handler) => subscribeBrowserChannel('history:append', handler),
    onDownload: (handler) => subscribeBrowserChannel('downloads:update', handler),
    onPermissionPrompt: (handler) => subscribeBrowserChannel('permissions:prompt', handler),
    onPermissionState: (handler) => subscribeBrowserChannel('permissions:state', handler),
    onSettings: (handler) => subscribeBrowserChannel('settings:state', handler),
    requestTabList: () => ipcRenderer.invoke('browser:request-tabs'),
    requestHistory: (limit) => ipcRenderer.invoke('history:list', { limit }),
    requestDownloads: (limit) => ipcRenderer.invoke('downloads:list', { limit }),
    showDownload: (id) => ipcRenderer.invoke('downloads:show-in-folder', { id }),
    getSettings: () => ipcRenderer.invoke('settings:get'),
    updateSettings: (patch) => ipcRenderer.invoke('settings:update', patch ?? {}),
    respondToPermission: (decision) => {
      if (!decision || typeof decision !== 'object') {
        return;
      }
      ipcRenderer.send('permissions:decision', decision);
    },
    listPermissions: (origin) => ipcRenderer.invoke('permissions:list', { origin }),
    clearPermission: (origin, permission) => ipcRenderer.invoke('permissions:clear', { origin, permission }),
    clearOriginPermissions: (origin) => ipcRenderer.invoke('permissions:clear-origin', { origin }),
    setPermission: (origin, permission, setting) =>
      ipcRenderer.invoke('permissions:set', { origin, permission, setting }),
    clearSiteData: (origin) => ipcRenderer.invoke('site:clear-data', { origin }),
  };
}

spoofNavigator();

contextBridge.exposeInMainWorld('desktop', {
  runSystemCheck: (options) => ipcRenderer.invoke('system-check:run', options ?? {}),
  getLastSystemCheck: () => ipcRenderer.invoke('system-check:last'),
  openSystemCheckReport: () => ipcRenderer.invoke('system-check:open-report'),
  exportSystemCheckReport: (options) => ipcRenderer.invoke('system-check:export-report', options ?? {}),
  onSystemCheckEvent: (channel, handler) => subscribe(channel, handler),
  shadowCapture: (payload) => ipcRenderer.invoke('shadow:capture', payload ?? {}),
  indexSearch: (query) => ipcRenderer.invoke('index:search', query ?? ''),
  onShadowToggle: (handler) => {
    if (typeof handler !== 'function') {
      return NOOP_UNSUBSCRIBE;
    }
    try {
      const listener = () => {
        try {
          handler();
        } catch (error) {
          console.warn('[desktop] Shadow toggle handler threw:', error);
        }
      };
      ipcRenderer.on('desktop:shadow-toggle', listener);
      return () => ipcRenderer.removeListener('desktop:shadow-toggle', listener);
    } catch (error) {
      console.warn('[desktop] Failed to subscribe to shadow toggle channel:', error);
      return NOOP_UNSUBSCRIBE;
    }
  },
});

contextBridge.exposeInMainWorld('browserAPI', createBrowserAPI());
