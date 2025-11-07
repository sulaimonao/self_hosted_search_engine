import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

type AnyRecord = Record<string, unknown>;
type VercelMessage = { role?: string; content?: unknown; parts?: unknown };

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

export async function POST(req: NextRequest) {
  // Translate Vercel AI SDK request into backend ChatRequest and proxy as SSE
  let incoming: unknown = null;
  try {
    incoming = await req.json();
  } catch {
    // tolerate non-JSON; treat as empty
    incoming = {};
  }

  const inc = (incoming && typeof incoming === 'object' ? (incoming as Record<string, unknown>) : {}) as Record<string, unknown>;
  const bodyObj = (typeof inc.body === 'object' && inc.body !== null ? (inc.body as Record<string, unknown>) : undefined);
  const modelRaw = (typeof inc.model === 'string' ? inc.model : typeof bodyObj?.model === 'string' ? (bodyObj!.model as string) : null);
  // Preserve exact tag if provided; backend can normalize/validate
  const model = (modelRaw || undefined) as string | undefined;

  // Extract last user message from AI SDK shape
  const messages = Array.isArray(inc.messages) ? (inc.messages as VercelMessage[]) : [];
  const lastUser = messages.filter((m) => (m?.role || '').toLowerCase() === 'user').pop();
  const fromMsg = lastUser ? extractText((lastUser as AnyRecord).content ?? (lastUser as AnyRecord).parts) : '';
  const textCandidate = fromMsg || (typeof inc['text'] === 'string' ? (inc['text'] as string) : '');
  const text = textCandidate.trim();
  // NEW: treat either a non-empty text field or a non-empty user message as valid
  const hasNonEmptyUser = !!text || messages.some(
    (m) =>
      (m?.role || '').toLowerCase() === 'user' &&
      typeof (m as AnyRecord).content !== 'undefined' &&
      extractText((m as AnyRecord).content ?? (m as AnyRecord).parts).trim().length > 0,
  );

  const accept = (req.headers.get('accept') || '').toLowerCase();
  const wantsNdjson = accept.includes('application/x-ndjson');

  const backend = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || 'http://127.0.0.1:5050';
  let upstream: Response;
  if (wantsNdjson) {
    // Pass through ChatRequest if present; otherwise synthesize from text
  const messagesPayload = Array.isArray(inc.messages)
      ? (inc.messages as Array<{ role?: unknown; content?: unknown; parts?: unknown }>).map((m) => ({
          role: typeof m.role === 'string' ? m.role : 'user',
          content: extractText(m.content ?? m.parts),
        }))
      : text
      ? [{ role: 'user', content: text }]
      : [];
  // Validation: reject only if neither text nor any user message is non-empty
  if (!hasNonEmptyUser) {
      return new Response(JSON.stringify({ error: 'EMPTY_MESSAGE' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    upstream = await fetch(`${backend}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson',
      },
      body: JSON.stringify({
        model,
        stream: true,
        messages: messagesPayload,
      }),
    });
  } else {
    // Backend SSE stream
  // Validation: reject only if neither text nor any user message is non-empty
  if (!hasNonEmptyUser) {
      return new Response(JSON.stringify({ error: 'EMPTY_MESSAGE' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const messagesPayload = Array.isArray(inc.messages)
      ? (inc.messages as Array<{ role?: unknown; content?: unknown; parts?: unknown }>).map((m) => ({
          role: typeof m.role === 'string' ? m.role : 'user',
          content: extractText(m.content ?? m.parts),
        }))
      : [{ role: 'user', content: text }];
    upstream = await fetch(`${backend}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        model,
        stream: true,
        messages: messagesPayload,
      }),
    });
  }

  // If backend errored, bubble up JSON body if possible, and normalize model-not-found shape
  if (!upstream.ok && (!upstream.body || (upstream.headers.get('content-type') || '').includes('application/json'))) {
    const text = await upstream.text();
    try {
      const json = JSON.parse(text) as Record<string, unknown>;
      if ((upstream.status === 503 || upstream.status === 404) && (json?.error === 'model_not_found' || json?.error === 'MODEL_NOT_FOUND')) {
        const resp = { error: 'MODEL_NOT_FOUND', model: (json.model as string | undefined) ?? (Array.isArray(json.tried) ? (json.tried as string[])[0] : undefined) };
        return new Response(JSON.stringify(resp), { status: 400, headers: { 'Content-Type': 'application/json' } });
      }
    } catch {
      // fall through to raw passthrough
    }
    return new Response(text, {
      status: upstream.status,
      headers: { 'Content-Type': upstream.headers.get('content-type') || 'application/json' },
    });
  }

  // Pass SSE through unchanged with stable streaming headers for AI SDK
  const res = new Response(upstream.body, {
    status: upstream.status,
    headers: wantsNdjson
      ? {
          'Content-Type': 'application/x-ndjson',
          'Cache-Control': 'no-store',
          'Access-Control-Expose-Headers': '*',
        }
      : {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache, no-transform',
          Connection: 'keep-alive',
          'X-Accel-Buffering': 'no',
          'Access-Control-Expose-Headers': '*',
        },
  });
  return res;
}
