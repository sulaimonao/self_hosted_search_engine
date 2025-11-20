import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const incoming = request.headers.get('x-correlation-id');
  const correlationId = incoming && incoming.trim().length > 0 ? incoming : crypto.randomUUID();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-correlation-id', correlationId);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  response.headers.set('x-correlation-id', correlationId);
  return response;
}

export const config = {
  matcher: ['/api/:path*'],
};
