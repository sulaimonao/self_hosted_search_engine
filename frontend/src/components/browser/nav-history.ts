// frontend/src/components/browser/nav-history.ts

export type NavEntry = { url: string };

export class NavHistory {
  private stack: NavEntry[] = [];
  private idx = -1;

  current(): string {
    return this.stack[this.idx]?.url ?? "";
  }

  canBack(): boolean {
    return this.idx > 0;
  }

  canForward(): boolean {
    return this.idx >= 0 && this.idx < this.stack.length - 1;
  }

  push(rawUrl: string): void {
    const url = rawUrl?.trim();
    if (!url) {
      return;
    }
    this.stack = this.stack.slice(0, this.idx + 1);
    this.stack.push({ url });
    this.idx = this.stack.length - 1;
  }

  back(): string {
    if (this.canBack()) {
      this.idx -= 1;
    }
    return this.current();
  }

  forward(): string {
    if (this.canForward()) {
      this.idx += 1;
    }
    return this.current();
  }

  reset(rawUrl?: string): void {
    this.stack = [];
    this.idx = -1;
    if (rawUrl) {
      this.push(rawUrl);
    }
  }

  // Legacy aliases kept for compatibility with older call sites.
  canFwd(): boolean {
    return this.canForward();
  }

  fwd(): string {
    return this.forward();
  }
}
