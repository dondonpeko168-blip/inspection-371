// Edge Middleware: apply Basic Auth to all routes EXCEPT /api/upload
const BASIC_USER = process.env.BASIC_AUTH_USER;
const BASIC_PASS = process.env.BASIC_AUTH_PASS;

// Paths that don't need auth
const PUBLIC_PATHS = ['/api/upload', '/api/upload-url', '/api/upload-complete'];

export default function middleware(request) {
  // Always allow upload endpoints (no auth)
  const pathname = new URL(request.url).pathname;
  if (PUBLIC_PATHS.some(p => pathname === p)) {
    return;
  }

  // Apply Basic Auth to everything else
  if (BASIC_USER && BASIC_PASS) {
    const authHeader = request.headers.get('authorization');
    if (!authHeader || !authHeader.startsWith('Basic ')) {
      return respondUnauthorized();
    }
    const encoded = authHeader.slice(6);
    const decoded = Buffer.from(encoded, 'base64').toString('utf-8');
    const [user, pass] = decoded.split(':');
    if (user !== BASIC_USER || pass !== BASIC_PASS) {
      return respondUnauthorized();
    }
  }

  return;
}

function respondUnauthorized() {
  const response = new Response('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="inspection-371"' },
  });
  return response;
}

export const config = {
  matcher: [
    // Match all paths except static assets and Next.js internals
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};