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
  }
}
