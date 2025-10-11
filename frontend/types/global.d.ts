export {};

declare global {
  interface Window {
    omni?: {
      openUrl: (url: string) => Promise<void>;
      openPath?: (path: string | null | undefined) => Promise<void>;
      pickDir: () => Promise<string | null>;
      onViewerFallback: (fn: (payload: { url: string }) => void) => void | (() => void);
      quit: () => Promise<void>;
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
      onSystemCheckEvent?: (channel: string, handler: (payload: unknown) => void) => (() => void) | void;
    };
  }
}

type ElectronWebviewElement = HTMLElement & {
  reload?: () => void;
  loadURL?: (url: string) => void;
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
