// Edge Function: 強制讓 /api/upload 的 OPTIONS 回 200
// 讓 Vercel rewrite 處理 GET/POST，Edge 處理 OPTIONS preflight
export const config = {
  matcher: ['/api/upload', '/api/upload-url', '/api/upload-complete'],
};

export default async function handler(req) {
  const url = new URL(req.url);

  // OPTIONS preflight — always return 200 with CORS headers
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, X-Requested-With',
        'Access-Control-Max-Age': '86400',
      },
    });
  }

  // For actual GET/POST: return 404 so Vercel rewrite → Python serverless
  return new Response('Not Handled', { status: 404 });
}