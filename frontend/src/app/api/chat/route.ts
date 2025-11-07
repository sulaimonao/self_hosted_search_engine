import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

type VercelMessage = { role?: string; content?: string };

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
  const textCandidate = typeof lastUser?.content === 'string' ? lastUser!.content : typeof inc['text'] === 'string' ? (inc['text'] as string) : '';
  const text = textCandidate.trim();

  const accept = (req.headers.get('accept') || '').toLowerCase();
  const wantsNdjson = accept.includes('application/x-ndjson');

  const backend = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || 'http://127.0.0.1:5050';
  let upstream: Response;
  if (wantsNdjson) {
    // Pass through ChatRequest if present; otherwise synthesize from text
    const messagesPayload = Array.isArray(inc.messages)
      ? (inc.messages as Array<{ role?: unknown; content?: unknown }>).map((m) => ({
          role: typeof m.role === 'string' ? m.role : 'user',
          content: typeof m.content === 'string' ? m.content : '',
        }))
      : text
      ? [{ role: 'user', content: text }]
      : [];
    if (messagesPayload.length === 0) {
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
    if (!text && !Array.isArray(inc.messages)) {
      return new Response(JSON.stringify({ error: 'EMPTY_MESSAGE' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    const messagesPayload = Array.isArray(inc.messages)
      ? (inc.messages as Array<{ role?: unknown; content?: unknown }>).map((m) => ({
          role: typeof m.role === 'string' ? m.role : 'user',
          content: typeof m.content === 'string' ? m.content : '',
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

  // If backend errored, bubble up JSON body if possible
  if (!upstream.ok && (!upstream.body || (upstream.headers.get('content-type') || '').includes('application/json'))) {
    return new Response(await upstream.text(), {
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
