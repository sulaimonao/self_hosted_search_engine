
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
  if (!iframe) return;
  if (!canAccess(iframe)) return;
  try { iframe.contentWindow?.history.back(); } catch {}
}

export function forward(iframe: IframeLike): void {
  if (!iframe) return;
  if (!canAccess(iframe)) return;
  try { iframe.contentWindow?.history.forward(); } catch {}
}

export function reload(iframe: IframeLike): void {
  if (!iframe) return;
  try {
    iframe.contentWindow?.location.reload();
  } catch {
    try {
      const src = iframe.getAttribute('src');
      if (src) iframe.setAttribute('src', src);
    } catch {}
  }
}

export function setSrc(iframe: IframeLike, url: string): void {
  if (!iframe) return;
  try { iframe.setAttribute('src', url); } catch {}
}

export function canNavigate(iframe: IframeLike): boolean {
  return canAccess(iframe);
}
