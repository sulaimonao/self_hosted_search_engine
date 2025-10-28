// frontend/src/components/browser/nav-history.ts

export type NavEntry = { url: string };
export class NavHistory {
  private stack: NavEntry[] = [];
  private idx = -1;

  current() { return this.stack[this.idx]?.url ?? ""; }
  canBack() { return this.idx > 0; }
  canFwd()  { return this.idx >= 0 && this.idx < this.stack.length - 1; }

  push(url: string) {
    this.stack = this.stack.slice(0, this.idx + 1);
    this.stack.push({ url });
    this.idx = this.stack.length - 1;
  }
  back() { if (this.canBack()) this.idx--; return this.current(); }
  fwd()  { if (this.canFwd())  this.idx++; return this.current(); }
}

// Safe helpers for real iframe history (no-throw on cross-origin)
export type IframeLike = HTMLIFrameElement | null | undefined;

function canAccess(iframe: IframeLike): boolean {
  try {
    void iframe?.contentWindow?.location?.href;
    void iframe?.contentWindow?.history;
    return true;
  } catch {
    return false;
  }
}

export function back(iframe: IframeLike): void {
  if (!iframe || !canAccess(iframe)) return;
  try { iframe.contentWindow?.history.back(); } catch {}
}

export function forward(iframe: IframeLike): void {
  if (!iframe || !canAccess(iframe)) return;
  try { iframe.contentWindow?.history.forward(); } catch {}
}

export function reload(iframe: IframeLike): void {
  if (!iframe) return;
  try {
    iframe.contentWindow?.location.reload();
  } catch {
    try {
      const src = iframe.getAttribute("src");
      if (src) iframe.setAttribute("src", src);
    } catch {}
  }
}

export function setSrc(iframe: IframeLike, url: string): void {
  if (!iframe) return;
  try { iframe.setAttribute("src", url); } catch {}
}

export function canNavigate(iframe: IframeLike): boolean {
  return canAccess(iframe);
}
