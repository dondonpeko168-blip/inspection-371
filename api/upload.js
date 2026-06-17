// Edge Function: 搶在 Vercel proxy 之前處理 CORS preflight
// 當 Edge Function 攔截 OPTIONS，直接回 200 + CORS headers
// POST/GET 由 Vercel rewrite → Python serverless function

export const config = {
  matcher: ['/api/upload', '/api/upload-file', '/api/upload-url', '/api/upload-complete'],
};

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
      },
    });
  }
  // For non-OPTIONS: do NOT forward with fetch() — let Vercel rewrite handle it
  // fetch() from Edge creates a loop. Instead, tell Vercel to route normally.
  // We return null body and let Vercel's rewrite rules handle GET/POST.
  return new Response('Not Handled', { status: 404 });
}