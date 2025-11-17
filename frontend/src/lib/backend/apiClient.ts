const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").replace(/\/$/, "");

export type ApiRequestOptions = RequestInit & {
  skipBase?: boolean;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details?: unknown;

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function resolveUrl(path: string, skipBase?: boolean) {
  if (skipBase || path.startsWith("http")) {
    return path;
  }
  if (!API_BASE) return path;
  return `${API_BASE}${path}`;
}

async function parseJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { skipBase, headers, ...rest } = options;
  const url = resolveUrl(path, skipBase);
  const response = await fetch(url, {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(rest.body ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string> | undefined),
    },
  });
  const payload = (await parseJson(response)) as Record<string, unknown> | string | null;
  if (!response.ok) {
    if (payload && typeof payload === "object") {
      const code = (payload.error && typeof payload.error === "object"
        ? (payload.error.code as string | undefined)
        : undefined) ?? (payload.error as string | undefined);
      const message =
        (payload.error && typeof payload.error === "object"
          ? (payload.error.message as string | undefined)
          : undefined) ??
        (typeof payload.message === "string" ? payload.message : undefined) ??
        response.statusText;
      throw new ApiError(message || "Request failed", response.status, code, payload.error?.details ?? payload.details);
    }
    throw new ApiError(response.statusText || "Request failed", response.status);
  }
  if (payload && typeof payload === "object" && "ok" in payload) {
    if (!payload.ok) {
      const error = (payload.error ?? {}) as { code?: string; message?: string; details?: unknown };
      throw new ApiError(error.message || "Request failed", response.status, error.code, error.details);
    }
    if ("data" in payload) {
      return (payload.data ?? payload) as T;
    }
  }
  return payload as T;
}

export const apiClient = {
  get: <T>(path: string, options?: ApiRequestOptions) => request<T>(path, { ...options, method: "GET" }),
  delete: <T>(path: string, options?: ApiRequestOptions) => request<T>(path, { ...options, method: "DELETE" }),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, {
      ...options,
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : options?.body,
    }),
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, {
      ...options,
      method: "PUT",
      body: body !== undefined ? JSON.stringify(body) : options?.body,
    }),
  patch: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, {
      ...options,
      method: "PATCH",
      body: body !== undefined ? JSON.stringify(body) : options?.body,
    }),
};

export type ApiClient = typeof apiClient;
