export {};

declare global {
  interface Window {
    omni?: {
      openUrl?: (url: string) => Promise<void> | void;
      openPath?: (path: string | null | undefined) => Promise<void> | void;
      pickDir?: () => Promise<string | null>;
      onViewerFallback?: (
        fn: (payload: { url?: string | null }) => void,
      ) => void | (() => void);
      quit?: () => Promise<void> | void;
    };
    appBridge?: {
      onNavProgress?: (
        callback: (event: { stage?: string; url?: string; status?: number; tabId?: number }) => void,
      ) => (() => void) | void;
      setShadowMode?: (enabled: boolean) => void;
      supportsWebview?: boolean;
    };
    desktop?: {
      runSystemCheck?: (options?: { timeoutMs?: number }) => Promise<unknown>;
      getLastSystemCheck?: () => Promise<unknown>;
      openSystemCheckReport?: () => Promise<unknown>;
      exportSystemCheckReport?: (options?: { timeoutMs?: number; write?: boolean }) => Promise<unknown>;
      shadowCapture?: (payload: Record<string, unknown>) => Promise<unknown>;
      indexSearch?: (query: string) => Promise<unknown>;
      onSystemCheckEvent?: (channel: string, handler: (payload: unknown) => void) => (() => void) | void;
      onShadowToggle?: (handler: () => void) => (() => void) | void;
    };
  }
}

type ElectronWebviewElement = HTMLElement & {
  reload?: () => void;
  loadURL?: (url: string) => void | Promise<void>;
  stop?: () => void;
  goBack?: () => void;
  goForward?: () => void;
  canGoBack?: () => boolean;
  canGoForward?: () => boolean;
  getURL?: () => string;
  getTitle?: () => string;
  executeJavaScript?: <T = unknown>(code: string, userGesture?: boolean) => Promise<T>;
  addEventListener?: (type: string, listener: (...args: unknown[]) => void) => void;
  removeEventListener?: (type: string, listener: (...args: unknown[]) => void) => void;
};

declare global {
  namespace JSX {
    interface IntrinsicElements {
      webview: React.DetailedHTMLProps<React.HTMLAttributes<ElectronWebviewElement>, ElectronWebviewElement> & {
        src?: string;
        allowpopups?: boolean;
        partition?: string;
      };
    }
  }
}

declare module "@shared/browser-diagnostics-script" {
  export const BROWSER_DIAGNOSTICS_SCRIPT: string;
}
