export type NavEntry = {
  url: string;
};

export class NavHistory {
  private stack: NavEntry[] = [];
  private index = -1;

  current(): string {
    return this.stack[this.index]?.url ?? "";
  }

  size(): number {
    return this.stack.length;
  }

  canBack(): boolean {
    return this.index > 0;
  }

  canForward(): boolean {
    return this.index >= 0 && this.index < this.stack.length - 1;
  }

  push(url: string): string {
    const normalized = url.trim();
    if (!normalized) {
      return this.current();
    }
    if (this.current() === normalized) {
      return normalized;
    }
    this.stack = this.stack.slice(0, this.index + 1);
    this.stack.push({ url: normalized });
    this.index = this.stack.length - 1;
    return normalized;
  }

  replace(url: string): string {
    const normalized = url.trim();
    if (!normalized) {
      this.reset();
      return "";
    }
    if (this.index === -1) {
      this.stack = [{ url: normalized }];
      this.index = 0;
      return normalized;
    }
    this.stack[this.index] = { url: normalized };
    return normalized;
  }

  back(): string | null {
    if (!this.canBack()) {
      return null;
    }
    this.index -= 1;
    return this.current();
  }

  forward(): string | null {
    if (!this.canForward()) {
      return null;
    }
    this.index += 1;
    return this.current();
  }

  reset(url?: string): string {
    this.stack = [];
    this.index = -1;
    if (url && url.trim()) {
      return this.push(url);
    }
    return "";
  }

  entries(): NavEntry[] {
    return [...this.stack];
  }
}
