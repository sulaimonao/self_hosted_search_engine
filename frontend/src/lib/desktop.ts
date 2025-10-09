declare global {
  interface Window {
    DesktopBridge?: unknown;
  }
}

export const desktop =
  typeof window !== "undefined" ? ((window as { DesktopBridge?: unknown }).DesktopBridge as any) : undefined;
