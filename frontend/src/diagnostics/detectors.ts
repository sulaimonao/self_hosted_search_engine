export type IncidentSymptoms = {
  bannerText?: string;
  consoleErrors?: string[];
  networkErrors?: { url: string; status?: number; error?: string }[];
};

export function installConsoleDetector(onErr: (msg: string) => void) {
  const origError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    try {
      onErr(String(args[0] ?? "console.error"));
    } catch {
      // ignore errors from diagnostics path
    }
    origError(...args);
  };
  window.addEventListener("error", (event: ErrorEvent) => {
    onErr(String(event?.message || "window.error"));
  });
  window.addEventListener("unhandledrejection", (event: PromiseRejectionEvent) => {
    const reason = (event?.reason as { message?: string } | undefined)?.message;
    onErr(String(reason || "unhandledrejection"));
  });
}

export function installNetworkDetector(
  onFail: (entry: { url: string; status?: number; error?: string }) => void,
) {
  const wrap = (orig: typeof fetch) =>
    async (...args: Parameters<typeof fetch>): Promise<Response> => {
      try {
        const res = await orig(...args);
        if (res && res.status >= 400) {
          onFail({ url: res.url, status: res.status });
        }
        return res;
      } catch (err: unknown) {
        const request = args?.[0];
        const targetUrl = typeof request === "string" ? request : (request as Request)?.url ?? "";
        onFail({ url: String(targetUrl), error: String(err) });
        throw err;
      }
    };
  const originalFetch = window.fetch.bind(window);
  (window as typeof window & { fetch: typeof fetch }).fetch = wrap(originalFetch);
}

export function scanDomForBanner(): string | undefined {
  const candidates = Array.from(
    document.querySelectorAll('[role="alert"], .toast, .error, .alert-error'),
  );
  const withError = candidates.find((el) => /error|failed|issue|\d+\s*error/i.test(el.textContent || ""));
  return withError?.textContent?.trim() || undefined;
}
