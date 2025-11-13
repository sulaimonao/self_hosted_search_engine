"use client";

/**
 * Resolve the default New Tab URL at runtime.
 * - Desktop (Electron BrowserView): must be an absolute URL the BrowserView can load
 * - Web fallback (iframe/webview): relative is fine, but we prefer absolute for consistency
 */
export function getDefaultNewTabUrl(): string {
  try {
    if (typeof window !== "undefined" && window.location && window.location.origin) {
      return `${window.location.origin}/graph`;
    }
  } catch {
    // ignore and return fallback below
  }
  // Safe fallback if window is not available during SSR
  return "/graph";
}
