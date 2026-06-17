// Edge Function搶在serverless function之前處理CORS preflight
// Edge Functions在Vercel Edge Network層級處理，繞過proxy的501問題
export const config = {
  matcher: ['/api/upload/:path*'],
};

export default function handler(req) {
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
  // For non-OPTIONS requests, continue to the origin (serverless function)
  return fetch(req);
}