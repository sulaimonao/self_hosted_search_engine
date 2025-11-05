import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

export async function POST(req: NextRequest) {
  // Proxy body and headers to local Flask server at 127.0.0.1:5050
  const body = await req.text();

  const headers: Record<string, string> = {};
  // forward select headers
  for (const [k, v] of req.headers.entries()) {
    if (typeof v === 'string') headers[k] = v;
  }

  const resp = await fetch('http://127.0.0.1:5050/api/chat', {
    method: 'POST',
    headers: {
      ...headers,
      // ensure JSON content-type is present for Flask
      'content-type': headers['content-type'] ?? 'application/json',
    },
    body,
  });

  // Stream response back to client preserving status and headers
  return new Response(resp.body, {
    status: resp.status,
    headers: resp.headers as HeadersInit,
  });
}
