import { createTextStreamResponse } from 'ai';
import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

type AnyRecord = Record<string, unknown>;
type VercelMessage = { role?: string; content?: unknown; parts?: unknown };

function isRecord(value: unknown): value is AnyRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function findFirstStringKey(source: AnyRecord, key: string): string {
  const stack: AnyRecord[] = [source];
  const seen = new Set<AnyRecord>();
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (seen.has(current)) {
      continue;
    }
    seen.add(current);
    const candidate = current[key];
    if (typeof candidate === "string" && candidate.length > 0) {
      return candidate;
    }
    for (const value of Object.values(current)) {
      if (!value || typeof value !== "object") {
        continue;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          if (isRecord(item)) {
            stack.push(item);
          }
        }
      } else if (isRecord(value)) {
        stack.push(value);
      }
    }
  }
  return "";
}

function findAutopilotRecord(source: AnyRecord): AnyRecord | null {
  const stack: AnyRecord[] = [source];
  const seen = new Set<AnyRecord>();
  while (stack.length > 0) {
    const current = stack.pop()!;
    if (seen.has(current)) {
      continue;
    }
    seen.add(current);
    const candidate = current.autopilot;
    if (isRecord(candidate)) {
      return candidate;
    }
    for (const value of Object.values(current)) {
      if (!value || typeof value !== "object") {
        continue;
      }
      if (Array.isArray(value)) {
        for (const item of value) {
          if (isRecord(item)) {
            stack.push(item);
          }
        }
      } else if (isRecord(value)) {
        stack.push(value);
      }
    }
  }
  return null;
}

function extractText(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) {
    return value
      .map((v) => extractText(v))
      .filter(Boolean)
      .join('')
      .trim();
  }
  if (value && typeof value === 'object') {
    const obj = value as AnyRecord;
    if (typeof obj.text === 'string') return obj.text.trim();
    if (obj.content !== undefined) return extractText(obj.content);
    if (Array.isArray(obj.parts)) return extractText(obj.parts);
  }
  return '';
}

function formatResponseText(payload: unknown, fallback: string): string {
  if (!isRecord(payload)) {
    return fallback;
  }

  const answer = findFirstStringKey(payload, 'answer');
  const message = findFirstStringKey(payload, 'message');
  const reasoning = findFirstStringKey(payload, 'reasoning');
  const textField = findFirstStringKey(payload, 'text');

  const base = answer || message || reasoning || textField || '';
  if (!base) {
    return fallback;
  }

  const autopilot = findAutopilotRecord(payload);
  if (autopilot) {
    const mode = typeof autopilot.mode === 'string' ? autopilot.mode.trim() : '';
    const query = typeof autopilot.query === 'string' ? autopilot.query.trim() : '';
    const reason = typeof autopilot.reason === 'string' ? autopilot.reason.trim() : '';
    const toolHints = Array.isArray(autopilot.tools)
      ? autopilot.tools
          .map((entry) => (isRecord(entry) && typeof entry.label === 'string' ? entry.label.trim() : ''))
          .filter(Boolean)
      : [];
    const autopilotHint = [
      mode && `mode: ${mode}`,
      query && `query: ${query}`,
      reason && `reason: ${reason}`,
      toolHints.length > 0 && `tools: ${toolHints.join('|')}`,
    ]
      .filter(Boolean)
      .join(', ');
    if (autopilotHint) {
      return `${base}\n\n[Autopilot] ${autopilotHint}`;
    }
  }

  return base;
}

function cloneBody(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined;
  }
  return { ...(value as Record<string, unknown>) };
}

async function maybeReturnStreamingError(upstream: Response): Promise<Response | null> {
  const contentType = (upstream.headers.get('content-type') || '').toLowerCase();
  if (!upstream.ok && (!upstream.body || contentType.includes('application/json'))) {
    const text = await upstream.text();
    try {
      const json = JSON.parse(text) as Record<string, unknown>;
      if (
        (upstream.status === 503 || upstream.status === 404) &&
        (json?.error === 'model_not_found' || json?.error === 'MODEL_NOT_FOUND')
      ) {
        const resp = {
          error: 'MODEL_NOT_FOUND',
          model: (json.model as string | undefined) ?? (Array.isArray(json.tried) ? (json.tried as string[])[0] : undefined),
        };
        return new Response(JSON.stringify(resp), { status: 400, headers: { 'Content-Type': 'application/json' } });
      }
      return new Response(JSON.stringify(json), {
        status: upstream.status,
        headers: { 'Content-Type': 'application/json' },
      });
    } catch {
      return new Response(text, {
        status: upstream.status,
        headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
      });
    }
  }
  return null;
}

function buildMessages(payload: unknown, fallbackText: string): Array<{ role: string; content: string }> {
  if (Array.isArray(payload)) {
    return (payload as VercelMessage[]).map((m) => ({
      role: typeof m.role === 'string' && m.role.trim() ? m.role : 'user',
      content: extractText((m as AnyRecord).content ?? (m as AnyRecord).parts),
    }));
  }
  if (fallbackText.trim()) {
    return [{ role: 'user', content: fallbackText.trim() }];
  }
  return [];
}

export async function POST(req: NextRequest) {
  let incoming: unknown = null;
  try {
    incoming = await req.json();
  } catch {
    incoming = {};
  }

  const inc = (incoming && typeof incoming === 'object' ? (incoming as Record<string, unknown>) : {}) as Record<string, unknown>;
  const bodyObj = cloneBody(inc.body);
  const modelRaw = (typeof inc.model === 'string' ? inc.model : typeof bodyObj?.model === 'string' ? (bodyObj!.model as string) : null);
  const model = (modelRaw || undefined) as string | undefined;

  const messages = Array.isArray(inc.messages) ? (inc.messages as VercelMessage[]) : [];
  const lastUser = messages.filter((m) => (m?.role || '').toLowerCase() === 'user').pop();
  const fromMsg = lastUser ? extractText((lastUser as AnyRecord).content ?? (lastUser as AnyRecord).parts) : '';
  const textCandidate = fromMsg || (typeof inc['text'] === 'string' ? (inc['text'] as string) : '');
  const text = textCandidate.trim();

  const messagesPayload = buildMessages(inc.messages, text);
  const hasNonEmptyUser = messagesPayload.some((m) => m.role.toLowerCase() === 'user' && m.content.trim().length > 0);
  if (!hasNonEmptyUser) {
    return new Response(JSON.stringify({ error: 'EMPTY_MESSAGE' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const accept = (req.headers.get('accept') || '').toLowerCase();
  const wantsNdjson = accept.includes('application/x-ndjson');
  const wantsSse = accept.includes('text/event-stream');
  const backend = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || 'http://127.0.0.1:5050';

  const basePayload: Record<string, unknown> = bodyObj ? { ...bodyObj } : {};
  if (model && typeof basePayload.model !== 'string') {
    basePayload.model = model;
  }

  const makePayload = (stream: boolean) => ({
    ...basePayload,
    messages: messagesPayload,
    stream,
  });

  if (wantsNdjson) {
    const upstream = await fetch(`${backend}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson',
      },
      body: JSON.stringify(makePayload(true)),
    });

    const error = await maybeReturnStreamingError(upstream);
    if (error) return error;

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': 'application/x-ndjson',
        'Cache-Control': 'no-store',
        'Access-Control-Expose-Headers': '*',
      },
    });
  }

  if (wantsSse) {
    const upstream = await fetch(`${backend}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify(makePayload(true)),
    });

    const error = await maybeReturnStreamingError(upstream);
    if (error) return error;

    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache, no-transform',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
        'Access-Control-Expose-Headers': '*',
      },
    });
  }

  const upstream = await fetch(`${backend}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(makePayload(false)),
  });

  if (!upstream.ok) {
    const errorText = await upstream.text();
    const headers = new Headers({
      'Content-Type': upstream.headers.get('content-type') || 'application/json',
    });
    const modelHeader = upstream.headers.get('x-llm-model');
    const requestId = upstream.headers.get('x-request-id');
    if (modelHeader) headers.set('X-LLM-Model', modelHeader);
    if (requestId) headers.set('X-Request-Id', requestId);
    return new Response(errorText, { status: upstream.status, headers });
  }

  const rawBody = await upstream.text();
  let parsed: unknown = rawBody;
  try {
    parsed = JSON.parse(rawBody) as AnyRecord;
  } catch {
    // fall back to raw text
  }

  const textResponse =
    typeof parsed === 'string'
      ? (parsed.length > 0 ? parsed : rawBody)
      : (() => {
          const candidate = formatResponseText(parsed, rawBody);
          return candidate.length > 0 ? candidate : rawBody;
        })();

  const headers = new Headers({
    'Cache-Control': 'no-store',
    'Access-Control-Expose-Headers': '*',
  });
  const modelHeader = upstream.headers.get('x-llm-model');
  const requestId = upstream.headers.get('x-request-id');
  if (modelHeader) headers.set('X-LLM-Model', modelHeader);
  if (requestId) headers.set('X-Request-Id', requestId);

  const stream = new ReadableStream<string>({
    start(controller) {
      controller.enqueue(textResponse);
      controller.close();
    },
  });

  return createTextStreamResponse({ headers, textStream: stream });
}
