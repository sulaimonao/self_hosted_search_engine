"use client";

/**
 * Runtime instrumentation for capturing browser incidents.
 *
 * The script runs in the renderer and emits structured incident payloads via
 * `window.postMessage` so higher-level diagnostics surfaces (like
 * `IncidentBus`) can subscribe without directly monkey-patching global APIs.
 */

type IncidentSeverity = "info" | "warn" | "error";

type IncidentDetail = Record<string, unknown>;

type IncidentMessage = {
  source: typeof INCIDENT_SOURCE;
  type: typeof INCIDENT_EVENT;
  payload: {
    kind: string;
    message?: string;
    severity: IncidentSeverity;
    detail?: IncidentDetail;
    ts: number;
  };
};

declare global {
  interface Window {
    __diagnosticsInstrumentation__?: boolean;
  }
}

const INCIDENT_SOURCE = "diagnostics::browser" as const;
const INCIDENT_EVENT = "diagnostics:incident" as const;
const POLL_STORM_THRESHOLD_MS = 3000;
const RENDER_LOOP_MUTATION_THRESHOLD = 200;
const RENDER_LOOP_WINDOW_MS = 2000;
const INCIDENT_THROTTLE_MS = 1500;

const overlaySelectors = [
  "#next-build-error",
  "#__next-build-error",
  "#webpack-dev-server-client-overlay",
  "#webpack-dev-server-client-overlay div",
  ".nextjs-toast",
  ".nextjs-error-overlay",
  ".react-error-overlay",
  "#nextjs__container",
];

const emissionTimestamps = new Map<string, number>();

const normaliseDetail = (detail: IncidentDetail | undefined): IncidentDetail | undefined => {
  if (!detail) {
    return undefined;
  }
  const result: IncidentDetail = {};
  for (const [key, value] of Object.entries(detail)) {
    try {
      if (value === undefined) {
        continue;
      }
      if (typeof value === "string") {
        result[key] = value.length > 512 ? `${value.slice(0, 509)}...` : value;
      } else if (typeof value === "number" || typeof value === "boolean" || value === null) {
        result[key] = value;
      } else {
        result[key] = JSON.parse(JSON.stringify(value));
      }
    } catch {
      result[key] = String(value);
    }
  }
  return Object.keys(result).length > 0 ? result : undefined;
};

const stringFromArgs = (args: unknown[]): string => {
  const parts = args.map((item) => {
    if (typeof item === "string") {
      return item;
    }
    if (item instanceof Error) {
      return `${item.name}: ${item.message}`;
    }
    try {
      return JSON.stringify(item);
    } catch {
      return String(item);
    }
  });
  const text = parts.join(" ").trim();
  return text.length > 0 ? text : "unknown_error";
};

const shouldThrottle = (key: string, throttleMs: number): boolean => {
  const now = Date.now();
  const last = emissionTimestamps.get(key);
  if (typeof last === "number" && now - last < throttleMs) {
    return true;
  }
  emissionTimestamps.set(key, now);
  return false;
};

const emitIncident = (
  kind: string,
  message: string | undefined,
  detail: IncidentDetail | undefined,
  severity: IncidentSeverity,
  throttleMs = INCIDENT_THROTTLE_MS,
) => {
  if (typeof window === "undefined") {
    return;
  }
  const key = `${kind}:${message ?? ""}`;
  if (shouldThrottle(key, throttleMs)) {
    return;
  }
  const payload: IncidentMessage = {
    source: INCIDENT_SOURCE,
    type: INCIDENT_EVENT,
    payload: {
      kind,
      message: message ? message.slice(0, 2000) : undefined,
      severity,
      detail: normaliseDetail(detail),
      ts: Date.now(),
    },
  };
  try {
    window.postMessage(payload, "*");
  } catch {
    // Swallow postMessage errors; diagnostics should never crash the host page.
  }
};

const installConsoleInstrumentation = () => {
  if (typeof window === "undefined") {
    return;
  }
  const originalError = window.console.error.bind(window.console);
  window.console.error = (...args: unknown[]) => {
    const message = stringFromArgs(args);
    emitIncident("CONSOLE_ERROR", message, undefined, "error");
    const loopDetected = /\[render-loop]/i.test(message) || /too many re-renders|maximum update depth exceeded/i.test(message);
    if (loopDetected) {
      emitIncident("RENDER_LOOP", message, undefined, "error", 5000);
    } else if (/hydration/i.test(message)) {
      emitIncident("HYDRATION_ERROR", message, undefined, "error", 5000);
    }
    originalError(...args);
  };

  window.addEventListener("error", (event) => {
    const message = event?.message || "window.error";
    emitIncident("CONSOLE_ERROR", String(message), undefined, "error");
    if (/hydration/i.test(String(message))) {
      emitIncident("HYDRATION_ERROR", String(message), undefined, "error", 5000);
    }
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = (event?.reason as { message?: string } | undefined)?.message ?? "unhandledrejection";
    emitIncident("CONSOLE_ERROR", String(reason), undefined, "error");
  });
};

const installOverlayObserver = () => {
  if (typeof window === "undefined" || typeof MutationObserver === "undefined") {
    return;
  }
  const seen = new Set<string>();
  const scan = () => {
    for (const selector of overlaySelectors) {
      const element = document.querySelector(selector) as HTMLElement | null;
      if (!element) {
        continue;
      }
      const text = element.textContent?.trim();
      if (!text) {
        continue;
      }
      const html = element.outerHTML.slice(0, 4000);
      const signature = `${selector}:${text.slice(0, 120)}`;
      if (seen.has(signature)) {
        continue;
      }
      seen.add(signature);
      const kind = /hydration/i.test(text) ? "HYDRATION_ERROR" : "REACT_OVERLAY";
      emitIncident(kind, text, { selector, html }, "error", 5000);
      break;
    }
  };
  const observer = new MutationObserver(() => {
    try {
      scan();
    } catch {
      // ignore observer errors
    }
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
  });
  // Initial scan in case the overlay already exists.
  setTimeout(scan, 0);
};

const installRenderLoopDetector = () => {
  if (typeof window === "undefined" || typeof MutationObserver === "undefined") {
    return;
  }
  let mutationCount = 0;
  const target =
    document.getElementById("__next") ||
    document.querySelector("[data-reactroot]") ||
    document.body;
  if (!target) {
    return;
  }
  const observer = new MutationObserver(() => {
    mutationCount += 1;
  });
  observer.observe(target, {
    childList: true,
    subtree: true,
    attributes: true,
  });
  window.setInterval(() => {
    if (mutationCount > RENDER_LOOP_MUTATION_THRESHOLD) {
      emitIncident(
        "RENDER_LOOP",
        `Detected ${mutationCount} DOM mutations within ${RENDER_LOOP_WINDOW_MS / 1000}s`,
        { mutations: mutationCount },
        "warn",
        5000,
      );
    }
    mutationCount = 0;
  }, RENDER_LOOP_WINDOW_MS);
};

const installPollStormDetector = () => {
  if (typeof window === "undefined") {
    return;
  }
  const originalSetInterval = window.setInterval.bind(window);
  window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
    const id = originalSetInterval(handler as TimerHandler, timeout as number, ...args);
    if (typeof timeout === "number" && timeout > 0 && timeout < POLL_STORM_THRESHOLD_MS) {
      const handlerPreview =
        typeof handler === "function" ? handler.name || handler.toString().slice(0, 60) : String(handler);
      emitIncident(
        "POLL_STORM",
        `setInterval scheduled at ${timeout}ms`,
        { timeout, handler: handlerPreview },
        timeout < 1000 ? "error" : "warn",
        0,
      );
    }
    return id;
  }) as typeof window.setInterval;
};

if (typeof window !== "undefined" && !window.__diagnosticsInstrumentation__) {
  window.__diagnosticsInstrumentation__ = true;
  installConsoleInstrumentation();
  installOverlayObserver();
  installRenderLoopDetector();
  installPollStormDetector();
}

export {};
